# ===============================================================
# router.py
# Multi-Signal Router for ModernBERT Scheduling NLU
# ===============================================================

from scheduler_engine import SchedulerNLU
from custom_exceptions import AmbiguityError, SlotConflictError
import torch
import torch.nn.functional as F
import numpy as np
import re
import time


class MultiSignalRouter:
    def __init__(self, nlu_engine: SchedulerNLU, centroids_path: str):
        self.nlu    = nlu_engine
        self.device = next(self.nlu.intent_model.parameters()).device

        self.centroids_tensor = None
        try:
            centroids = np.load(centroids_path)
            self.centroids_tensor = torch.tensor(centroids, dtype=torch.float32).to(self.device)
            print(f"[Router] Centroids loaded: {self.centroids_tensor.shape}")
        except Exception as e:
            print(f"[Router] Warning: Could not load centroids ({e}). OOD check bypassed.")

        self.complexity_patterns = {
            "conditional":       {"weight": 2, "patterns": ["if ", "unless", "depending on", "only if", "provided that", "assuming", "in case", "whether ", "as long as"]},
            "vague_time":        {"weight": 2, "patterns": ["sometime", "whenever", "at some point", "soon", "eventually", "at some stage", "whoever", "whatever time", "whenever i", "whenever i'm", "whenever i am"]},
            "relative_ops":      {"weight": 2, "patterns": ["move all", "reschedule everything", "cancel all", "delete all", "update all", "shift all", "block my calendar", "clear my calendar", "block the rest", "clear the rest", "all my afternoon", "all my morning"]},
            "conversational":    {"weight": 2, "patterns": ["do you think", "what do you think", "i feel like", "help me plan", "can you look at", "tell me if my", "would you suggest", "should i keep", "am i overbooked", "is my schedule", "looks reasonable", "too many meetings", "restructure my", "review my schedule", "balance my", "what would be the best", "is that too much", "based on my current schedule", "based on my schedule"]},
            "referential":       {"weight": 2, "patterns": ["we just talked about", "we just discussed", "we mentioned", "the one we", "that one we", "move it to", "reschedule it to", "cancel it", "delete it", "update it", "change it to", "those tasks", "those events", "those meetings", "the same one", "that same", " too$"]},
            "cross_domain_action":{"weight": 2, "patterns": ["and update the associated", "and invite the", "and also invite", "and update my availability", "and send a", "and email the"]},
            "multi_step":        {"weight": 1, "patterns": ["and then", "after that", "as well as", "and instead", "but also", "as well", "while also", "followed by", "and also", "and create", "and add", "and block", "and update", "and set", "and delete", "and cancel", "and remove", "and reschedule", "instead"]},
            "bulk_refs":         {"weight": 1, "patterns": ["all my", "every ", "everything", "all of my", "all the", "each of"]},
        }
        self.complexity_threshold = 2

        self._time_regex = re.compile(
            r'\b(\d{1,2}(:\d{2})?\s*(am|pm)|noon|midnight|'
            r'morning|afternoon|evening|tonight|'
            r'\d{1,2}\s*(hour|minute|min)s?\s*(before|after|later)|'
            r'(half|quarter)\s*(past|to)\s*\d{1,2})\b',
            re.IGNORECASE
        )

        self.question_starters = [
            "what are some", "how do i", "how can i", "can you explain", "tell me about",
            "give me tips", "give me advice", "why is ", "how to ", "could you explain",
            "do you know how", "can you teach me", "who won", "what films", "what movies",
            "can you help me write", "can you write me", "what is the capital",
            "what is the meaning", "how do you make", "what are the symptoms",
            "tell me the history", "what is the best way to learn", "give me a recipe",
            "what is the weather", "what should i eat", "what should i cook",
            "can you recommend a", "how does",
        ]

        self.scheduling_keywords = [
            "calendar", "event", "meeting", "task", "schedule", "appointment",
            "reminder", "standup", "sync", "free slot", "available", "busy",
            "booking", "session", "recurring", "recurrence", "agenda",
            "gym", "dentist", "lecture", "workshop", "review",
            "my interview", "the interview", "interview scheduled",
            "interview at", "interview on"
        ]

        self.required_slots = {
            "CREATE_EVENT":      ["events", "dates"],
            "UPDATE_EVENT":      [],
            "DELETE_EVENT":      ["events"],
            "QUERY_EVENT":       [],
            "FIND_FREE_TIME":    [],
            "SUGGEST_TIME":      [],
            "CHANGE_RECURRENCE": ["events", "recurrence"],
            "CREATE_TASK":       ["tasks"],
            "UPDATE_TASK":       [],
            "DELETE_TASK":       ["tasks"],
            "COMPLETE_TASK":     ["tasks"],
            "QUERY_TASK":        [],
            "SET_REMINDER":      [],
            "UPDATE_REMINDER":   [],
            "DELETE_REMINDER":   [],
            "SET_PREFERENCES":   [],
        }

        self.ood_similarity_threshold = 0.65
        self.min_entity_length        = 3
        self.margin_threshold         = 0.15


    def _is_conversational_continuation(self, text: str, chat_history: str) -> bool:
        """
        Returns True if the current input is most likely a follow-up to an
        ongoing chat conversation rather than a fresh scheduling command.

        Detection logic:
        1. Parse the last assistant turn from chat_history.
        2. If it looks like a scheduling action result, return False —
            the conversation reset to scheduling mode.
        3. If it looks conversational (no action language), check whether
            the current input has any scheduling keywords.
        4. If no scheduling keywords are present, this is a chat follow-up.
        """
        if not chat_history:
            return False

        # Parse the last assistant line from the formatted history string.
        # Format produced by _get_chat_history_string: "[Assistant]: ..."
        lines = [l.strip() for l in chat_history.strip().split("\n") if l.strip()]
        last_assistant_line = None
        for line in reversed(lines):
            if line.startswith("[Assistant]:"):
                last_assistant_line = line[len("[Assistant]:"):].strip().lower()
                break

        if not last_assistant_line:
            return False

        # These phrases indicate the last turn was a scheduling action result.
        # If present, the conversation has reset — don't apply continuation logic.
        action_indicators = [
            "i have scheduled", "i have created", "i have added",
            "i have deleted", "i have cancelled", "i have updated",
            "i have moved", "i have set a reminder", "i have marked",
            "i have removed", "i couldn't find", "you have",
            "you don't have", "you are free", "i suggest scheduling",
        ]
        if any(indicator in last_assistant_line for indicator in action_indicators):
            return False

        # The last assistant turn was conversational.
        # Now check if the current input has ANY scheduling intent.
        # If it does, let the router handle it normally.
        text_lower = text.lower()
        if any(kw in text_lower for kw in self.scheduling_keywords):
            return False

        # Additional scheduling verb check — catches direct commands
        # that don't contain a scheduling keyword noun but are clearly
        # scheduling requests ("book me in", "cancel that", "remind me").
        scheduling_verbs = [
            "schedule", "book", "create", "add", "delete", "remove",
            "cancel", "move", "reschedule", "remind me", "set a reminder",
            "what do i have", "when is my", "am i free",
        ]
        if any(verb in text_lower for verb in scheduling_verbs):
            return False

        # No scheduling signal found — this is a chat continuation
        print(f"[Router] Conversational continuation detected. Last assistant turn was chat.")
        return True

    def _is_interrogative_query(self, text: str) -> bool:
        text_lower = text.lower().strip()
        query_starters = ["is ", "are ", "do ", "does ", "has ", "have ", "can you tell me if",
                        "could you check if", "check if", "am i", "is the", "are the"]
        return any(text_lower.startswith(s) for s in query_starters) or text_lower.endswith("?")

    # CHANGED: added chat_history parameter — passed to nlu.llm_fallback so the
    # LLM receives recent conversation turns and can resolve pronouns and references.
    def _escalate_to_llm(self, text: str, reason: str, stage: int,
                            user_context: str = "", chat_history: str = "", user_timezone: str = "UTC") -> dict:
            # --- THE FIX: Pass user_timezone into llm_fallback ---
            llm_result = self.nlu.llm_fallback(text, reason, user_context, chat_history, user_timezone)

            if llm_result is None:
                return {
                    "source": "escalation_failed",
                    "intents": [], "entities": {}, "text": text,
                    "routing_meta": {
                        "escalation_reason": reason,
                        "escalation_stage":  stage,
                        "error": "LLM unavailable — no Gemini API key or request failed"
                    }
                }

            llm_result["routing_meta"] = {"escalation_reason": reason, "escalation_stage": stage}
            return llm_result

    def _is_general_question(self, text: str) -> bool:
        text_lower = text.lower().strip()
        if not any(text_lower.startswith(q) for q in self.question_starters):
            return False
        if any(kw in text_lower for kw in self.scheduling_keywords):
            return False
        return True

    def _get_complexity_score(self, text: str) -> int:
        score      = 0
        text_lower = text.lower()
        safe_phrases = ["what is my", "what's my", "whats my", "what does my",
                        "how is my", "show me my", "schedule like", "look like", "like on"]
        for phrase in safe_phrases:
            text_lower = text_lower.replace(phrase, "")
        for category, config in self.complexity_patterns.items():
            if any(p in text_lower for p in config["patterns"]):
                score += config["weight"]
                if score >= self.complexity_threshold:
                    return score
        return score

    def _embedding_similarity_check(self, text: str):
        if self.centroids_tensor is None:
            return True, 1.0
        inputs = self.nlu.tokenizer(text, return_tensors="pt", truncation=True, max_length=128).to(self.device)
        with torch.no_grad():
            outputs = self.nlu.intent_model(**inputs, output_hidden_states=True)
        cls_embedding = outputs.hidden_states[-1][:, 0, :]
        expanded      = cls_embedding.expand(self.centroids_tensor.shape[0], -1)
        similarities  = F.cosine_similarity(expanded, self.centroids_tensor, dim=1)
        max_sim       = torch.max(similarities).item()
        return max_sim >= self.ood_similarity_threshold, max_sim

    def _clean_entities(self, entities: dict) -> dict:
        cleaned = {}
        for key, values in entities.items():
            if not isinstance(values, list):
                cleaned[key] = values
                continue
            if key in ["dates", "times", "durations", "events", "tasks", "locations"]:
                cleaned[key] = [v.strip() for v in values if isinstance(v, str)]
                continue
            filtered = [v.strip() for v in values if isinstance(v, str) and len(v.strip()) >= self.min_entity_length]
            cleaned[key] = filtered
        return cleaned

    def _slot_fill_rate(self, intent_label: str, entities: dict) -> float:
        required = self.required_slots.get(intent_label, [])
        if not required:
            return 1.0
        filled = [s for s in required if entities.get(s) and len(entities[s]) > 0]
        return len(filled) / len(required)

    def _validate_reminder(self, entities: dict, raw_text: str) -> bool:
        if bool(entities.get("times")) or bool(entities.get("dates")) or bool(entities.get("reminders")):
            return True
        return bool(self._time_regex.search(raw_text))

    def _validate_delete_reminder(self, entities: dict) -> bool:
        return (bool(entities.get("reminders")) or bool(entities.get("events")) or
                bool(entities.get("dates")) or bool(entities.get("people")))

    def _run_intent_validation(self, intent: str, entities: dict, raw_text: str):
        if intent == "SET_REMINDER":
            if not self._validate_reminder(entities, raw_text):
                return False, "SET_REMINDER — no temporal signal extracted"
        if intent == "DELETE_REMINDER":
            if not self._validate_delete_reminder(entities):
                return False, "DELETE_REMINDER — no reference entity extracted"
        fill_rate = self._slot_fill_rate(intent, entities)
        if fill_rate == 0.0:
            return False, f"Zero slot fill for {intent} — likely misclassification"
        return True, None

    # CHANGED: added chat_history — threaded through all escalation call sites
        # and into nlu.process() so every LLM fallback path has conversation context.
    def evaluate(self, text: str, user_context: str = "", chat_history: str = "", user_timezone: str = "UTC") -> dict:
            # --- THE FIX: Thread user_timezone through all escalation paths ---
            
        if self._is_conversational_continuation(text, chat_history):
            return self._escalate_to_llm(
                text,
                reason="Conversational continuation — last assistant turn was chat",
                stage=0,
                user_context=user_context,
                chat_history=chat_history,
                user_timezone=user_timezone
            )

        if self._is_general_question(text):
            return self._escalate_to_llm(text, "General question — out of scheduling domain",
                                        stage=1, user_context=user_context, chat_history=chat_history, user_timezone=user_timezone)

        complexity = self._get_complexity_score(text)
        if complexity >= self.complexity_threshold:
            return self._escalate_to_llm(text, f"Linguistic complexity score: {complexity}",
                                        stage=2, user_context=user_context, chat_history=chat_history, user_timezone=user_timezone)

        in_domain, sim_score = self._embedding_similarity_check(text)
        if not in_domain:
            return self._escalate_to_llm(text, f"Out of domain — max similarity: {sim_score:.3f}",
                                        stage=3, user_context=user_context, chat_history=chat_history, user_timezone=user_timezone)

        # --- THE FIX: Pass user_timezone down to the ModernBERT process ---
        nlu_result = self.nlu.process(text, user_context=user_context, chat_history=chat_history, user_timezone=user_timezone)

        if nlu_result is None:
            return self._escalate_to_llm(text, "NLU engine returned None",
                                        stage=4, user_context=user_context, chat_history=chat_history, user_timezone=user_timezone)

        intents  = nlu_result.get("intents", [])
        entities = nlu_result.get("entities", {})
        scores   = nlu_result.get("confidence_scores", {})

        if not intents:
            return self._escalate_to_llm(text, "No intents met confidence threshold",
                                        stage=4, user_context=user_context, chat_history=chat_history, user_timezone=user_timezone)

        cleaned_entities       = self._clean_entities(entities)
        nlu_result["entities"] = cleaned_entities

        valid_intents       = []
        validation_failures = []

        for intent in intents:
            is_valid, reason = self._run_intent_validation(intent, cleaned_entities, text)

            if is_valid and self._is_interrogative_query(text):
                if intent in ["COMPLETE_TASK", "UPDATE_TASK", "DELETE_TASK"]:
                    intent = "QUERY_TASK"
                elif intent in ["COMPLETE_EVENT", "UPDATE_EVENT", "DELETE_EVENT"]:
                    intent = "QUERY_EVENT"

            if is_valid:
                valid_intents.append(intent)
            else:
                validation_failures.append((intent, reason))

        if not valid_intents:
            primary_reason = validation_failures[0][1] if validation_failures else "All intents failed validation"
            return self._escalate_to_llm(text, primary_reason,
                                        stage=6, user_context=user_context, chat_history=chat_history, user_timezone=user_timezone)

        nlu_result["intents"] = valid_intents

        if len(valid_intents) == 1:
            primary_intent = valid_intents[0]
            fill_rate      = self._slot_fill_rate(primary_intent, cleaned_entities)
            probs          = list(scores.values())
            if len(probs) >= 2:
                sorted_probs = sorted(probs, reverse=True)
                margin       = sorted_probs[0] - sorted_probs[1]
                if fill_rate < 1.0 and margin < self.margin_threshold:
                    return self._escalate_to_llm(text, f"Ambiguous: margin {margin:.2f}, fill {fill_rate:.2f}",
                                                stage=7, user_context=user_context, chat_history=chat_history, user_timezone=user_timezone)

        nlu_result["routing_meta"] = {
            "similarity_score":  round(sim_score, 3),
            "complexity_score":  complexity,
            "intents_detected":  intents,
            "intents_validated": valid_intents,
            "intents_dropped":   [f[0] for f in validation_failures],
        }

        return nlu_result


    def dispatch(self, nlu_result: dict, user_id: str, intent_handlers: dict) -> list:
        """
        CHANGED: catches AmbiguityError and SlotConflictError separately so the
        API layer receives structured clarification payloads rather than raw
        error strings — enabling the frontend to render selection/confirmation UI.
        """
        source   = nlu_result.get("source", "unknown")
        intents  = nlu_result.get("intents", [])
        entities = nlu_result.get("entities", {})
        text     = nlu_result.get("text", "")
        results  = []

        if source == "escalation_failed":
            return [{"intent": None, "result": None, "status": "error",
                     "error": nlu_result.get("routing_meta", {}).get("error", "Unknown escalation failure")}]

        chat_response = nlu_result.get("chat_response", "")
        if chat_response:
            return [{"intent": None, "result": chat_response, "status": "chat_response", "source": source}]

        for intent in intents:
            handler = intent_handlers.get(intent)
            if handler:
                try:
                    result = handler(entities, user_id, raw_text=text)
                    results.append({"intent": intent, "result": result, "status": "success", "source": source})

                except AmbiguityError as e:
                    # Multiple DB matches found - send candidates to frontend for selection.
                    # entity_key tells the frontend which entity array to replace when
                    # the user picks one, so it can re-submit via intent_override + entity_overrides.
                    results.append({
                        "intent":             intent,
                        "result":             None,
                        "status":             "clarification_needed",
                        "clarification_type": "ambiguous_match",
                        "message":            str(e),
                        "candidates":         e.candidates,
                        "query":              e.query,
                        "entity_key":         e.entity_key,
                        "source":             source,
                    })

                except SlotConflictError as e:
                    # Requested slot is booked — send conflict info plus the next
                    # available suggestion so the frontend can offer one-tap confirmation.
                    results.append({
                        "intent":             intent,
                        "result":             None,
                        "status":             "clarification_needed",
                        "clarification_type": "slot_conflict",
                        "message":            str(e),
                        "requested_start":    e.requested_start,
                        "requested_end":      e.requested_end,
                        "suggested_start":    e.suggested_start,
                        "suggested_end":      e.suggested_end,
                        "title":              e.title,
                        "source":             source,
                    })

                except Exception as e:
                    results.append({"intent": intent, "result": None, "status": "error", "error": str(e)})
            else:
                results.append({"intent": intent, "result": None, "status": "no_handler"})

        return results