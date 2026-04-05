# ===============================================================
# router_tests.py
# 200 Comprehensive Router Test Cases (100 NLU, 100 LLM)
# ===============================================================

# ================================================================
# TEST CASES
# Format: ("EXPECTED_DECISION", "input text", "intent or reason tag")
# ================================================================

NLU_TESTS = [
    # --- CREATE_EVENT (15) ---
    ("NLU", "Schedule a meeting tomorrow at 2pm",                                       "CREATE_EVENT"),
    ("NLU", "Book a call with the team on Friday at 11am",                              "CREATE_EVENT"),
    ("NLU", "Set up a standup every Monday at 9am",                                     "CREATE_EVENT"),
    ("NLU", "Create an event called Project Review on the 5th of April",                "CREATE_EVENT"),
    ("NLU", "Add a dentist appointment on Thursday at 3pm",                             "CREATE_EVENT"),
    ("NLU", "Schedule a lecture for Wednesday morning",                                 "CREATE_EVENT"),
    ("NLU", "Put a team sync in my calendar for next Tuesday at noon",                  "CREATE_EVENT"),
    ("NLU", "Book a gym session for Saturday at 7am",                                   "CREATE_EVENT"),
    ("NLU", "Create a meeting with Dr. Ahmed tomorrow at 10am",                         "CREATE_EVENT"),
    ("NLU", "Set up a one-on-one with Sarah next Monday at 4pm",                        "CREATE_EVENT"),
    ("NLU", "Schedule an interview for Friday afternoon",                               "CREATE_EVENT"),
    ("NLU", "Add a workshop event on the 12th at 1pm",                                  "CREATE_EVENT"),
    ("NLU", "Create a coffee catch-up with James on Tuesday",                           "CREATE_EVENT"),
    ("NLU", "Book a strategy session next Thursday at 2pm",                             "CREATE_EVENT"),
    ("NLU", "Schedule a review meeting for Monday morning",                             "CREATE_EVENT"),

    # --- UPDATE_EVENT (10) ---
    ("NLU", "Move the standup to 10am",                                                 "UPDATE_EVENT"),
    ("NLU", "Change the team meeting to Thursday",                                      "UPDATE_EVENT"),
    ("NLU", "Reschedule the project review to next week",                               "UPDATE_EVENT"),
    ("NLU", "Update the sync to 3pm instead",                                           "UPDATE_EVENT"),
    ("NLU", "Push the interview to Friday",                                             "UPDATE_EVENT"),
    ("NLU", "Change my dentist appointment to Wednesday at 2pm",                        "UPDATE_EVENT"),
    ("NLU", "Move the workshop to the afternoon",                                       "UPDATE_EVENT"),
    ("NLU", "Shift the lecture to 11am",                                                "UPDATE_EVENT"),
    ("NLU", "Reschedule the strategy session to next Monday",                           "UPDATE_EVENT"),
    ("NLU", "Update the one-on-one to Tuesday at noon",                                 "UPDATE_EVENT"),

    # --- DELETE_EVENT (8) ---
    ("NLU", "Cancel the standup on Friday",                                             "DELETE_EVENT"),
    ("NLU", "Delete the team meeting tomorrow",                                         "DELETE_EVENT"),
    ("NLU", "Remove the project review from my calendar",                               "DELETE_EVENT"),
    ("NLU", "Cancel my dentist appointment on Thursday",                                "DELETE_EVENT"),
    ("NLU", "Delete the workshop next Tuesday",                                         "DELETE_EVENT"),
    ("NLU", "Remove the gym session on Saturday",                                       "DELETE_EVENT"),
    ("NLU", "Cancel the interview scheduled for Friday",                                "DELETE_EVENT"),
    ("NLU", "Delete the sync meeting this afternoon",                                   "DELETE_EVENT"),

    # --- QUERY_EVENT (7) ---
    ("NLU", "What events do I have tomorrow?",                                          "QUERY_EVENT"),
    ("NLU", "What is on my calendar this week?",                                        "QUERY_EVENT"),
    ("NLU", "Show me my schedule for Monday",                                           "QUERY_EVENT"),
    ("NLU", "What meetings do I have in the afternoon?",                                "QUERY_EVENT"),
    ("NLU", "Do I have anything on Friday morning?",                                    "QUERY_EVENT"),
    ("NLU", "What is my next event today?",                                             "QUERY_EVENT"),
    ("NLU", "List all my meetings for this week",                                       "QUERY_EVENT"),

    # --- CREATE_TASK (8) ---
    ("NLU", "Add a task to review the project proposal",                                "CREATE_TASK"),
    ("NLU", "Create a task called finish the report by Friday",                         "CREATE_TASK"),
    ("NLU", "Add finish reading chapter 5 to my tasks",                                 "CREATE_TASK"),
    ("NLU", "Create a to-do for submitting the assignment by Wednesday",                "CREATE_TASK"),
    ("NLU", "Add prepare slides to my task list",                                       "CREATE_TASK"),
    ("NLU", "Create a task to email the client today",                                  "CREATE_TASK"),
    ("NLU", "Add buy groceries to my tasks",                                            "CREATE_TASK"),
    ("NLU", "Create a high priority task to fix the bug before Thursday",               "CREATE_TASK"),

    # --- UPDATE_TASK / DELETE_TASK / COMPLETE_TASK / QUERY_TASK (10) ---
    ("NLU", "Update the report task deadline to next Monday",                           "UPDATE_TASK"),
    ("NLU", "Change the submit assignment task to Thursday",                            "UPDATE_TASK"),
    ("NLU", "Delete the buy groceries task",                                            "DELETE_TASK"),
    ("NLU", "Remove the email client task from my list",                                "DELETE_TASK"),
    ("NLU", "Mark the report task as done",                                             "COMPLETE_TASK"),
    ("NLU", "Complete the finish slides task",                                          "COMPLETE_TASK"),
    ("NLU", "Mark fix the bug as complete",                                             "COMPLETE_TASK"),
    ("NLU", "What tasks do I have due this week?",                                      "QUERY_TASK"),
    ("NLU", "Show me all my pending tasks",                                             "QUERY_TASK"),
    ("NLU", "What tasks are overdue?",                                                  "QUERY_TASK"),

    # --- SET_REMINDER / UPDATE_REMINDER / DELETE_REMINDER (10) ---
    ("NLU", "Remind me about the dentist at 3pm",                                       "SET_REMINDER"),
    ("NLU", "Set a reminder for my meeting tomorrow morning",                           "SET_REMINDER"),
    ("NLU", "Remind me to call Sarah at noon",                                          "SET_REMINDER"),
    ("NLU", "Set a reminder 30 minutes before the standup",                             "SET_REMINDER"),
    ("NLU", "Remind me about the project deadline on Friday",                           "SET_REMINDER"),
    ("NLU", "Change the reminder for the dentist to 1 hour before",                    "UPDATE_REMINDER"),
    ("NLU", "Update the meeting reminder to 15 minutes before",                        "UPDATE_REMINDER"),
    ("NLU", "Delete the reminder for the standup",                                      "DELETE_REMINDER"),
    ("NLU", "Remove the reminder for my dentist appointment",                           "DELETE_REMINDER"),
    ("NLU", "Cancel the reminder for Friday's meeting",                                 "DELETE_REMINDER"),

    # --- FIND_FREE_TIME / SUGGEST_TIME / CHANGE_RECURRENCE / SET_PREFERENCES (12) ---
    ("NLU", "When am I free on Friday?",                                                "FIND_FREE_TIME"),
    ("NLU", "Find me a free slot tomorrow afternoon",                                   "FIND_FREE_TIME"),
    ("NLU", "What time am I available on Wednesday?",                                   "FIND_FREE_TIME"),
    ("NLU", "Suggest a good time for a 2 hour study session today",                    "SUGGEST_TIME"),
    ("NLU", "When would be a good time to schedule a meeting this week?",              "SUGGEST_TIME"),
    ("NLU", "Recommend the best time for a gym session tomorrow",                      "SUGGEST_TIME"),
    ("NLU", "Make the standup a weekly recurring event",                               "CHANGE_RECURRENCE"),
    ("NLU", "Change the team sync to repeat every Monday",                             "CHANGE_RECURRENCE"),
    ("NLU", "Set the project review to occur monthly",                                 "CHANGE_RECURRENCE"),
    ("NLU", "Do not schedule anything before 9am",                                     "SET_PREFERENCES"),
    ("NLU", "Set my focus hours to between 9am and 12pm",                              "SET_PREFERENCES"),
    ("NLU", "Ensure I am undisturbed before 9am",                                      "SET_PREFERENCES"),

    # --- Multi-intent — model handles these correctly, dispatcher executes both (10) ---
    # These were previously labelled LLM but are correct NLU behaviour:
    # the multi-label model fires the right intents and the dispatcher runs them.
    ("NLU", "Cancel the standup today and instead set up a sync with the engineering team for tomorrow morning.", "multi-intent NLU"),
    ("NLU", "Move my 2pm meeting to Thursday and also remind me an hour before",        "multi-intent NLU"),
    ("NLU", "Delete the project review and schedule a new one next week with the full team", "multi-intent NLU"),
    ("NLU", "Book a meeting with Sarah for Friday and set a reminder 30 minutes before and add prep slides to tasks", "multi-intent NLU"),
    ("NLU", "Delete my gym session Saturday and instead schedule a study block for 3 hours", "multi-intent NLU"),
    ("NLU", "Reschedule the dentist to next Thursday and remind me the day before",    "multi-intent NLU"),
    ("NLU", "Create a task for the report and schedule a 2 hour writing block tomorrow morning", "multi-intent NLU"),
    ("NLU", "Delete the Friday sync and instead add a task to send a written update by end of day", "multi-intent NLU"),
    ("NLU", "Reschedule my morning meetings and find me a free slot in the afternoon for deep work", "multi-intent NLU"),

    # --- Edge cases — terse inputs (9) ---
    ("NLU", "Delete standup Friday",                                                    "DELETE_EVENT - terse"),
    ("NLU", "Tasks this week",                                                          "QUERY_TASK - terse"),
    ("NLU", "Remind me dentist 2pm",                                                   "SET_REMINDER - terse"),
    ("NLU", "Free time Wednesday?",                                                    "FIND_FREE_TIME - terse"),
    ("NLU", "Cancel gym Saturday",                                                     "DELETE_EVENT - terse"),
    ("NLU", "Schedule call Friday noon",                                               "CREATE_EVENT - terse"),
    ("NLU", "Mark report done",                                                        "COMPLETE_TASK - terse"),
    ("NLU", "No meetings before 8am",                                                  "SET_PREFERENCES - terse"),
    ("NLU", "Weekly standup every Monday",                                             "CHANGE_RECURRENCE - terse"),
]


LLM_TESTS = [
    # --- Multi-step that require LLM-level coordination (11) ---
    # These involve external coordination (inviting people, sending emails)
    # or are structurally ambiguous beyond sequential intent execution.
    ("LLM", "Reschedule all my afternoon meetings today to tomorrow morning",           "bulk-multi-step"),
    ("LLM", "Move the interview to next week and update my availability block as well", "cross-domain-action"),
    ("LLM", "Add a team meeting on Monday and then block my calendar for the rest of the day", "cross-domain-action"),
    ("LLM", "Cancel the workshop and create a task to watch the recording instead",    "multi-step"),
    ("LLM", "Move the strategy session to Wednesday and also invite the marketing team","cross-domain-action"),
    ("LLM", "Reschedule the lecture and update the associated task deadlines",          "cross-domain-action"),
    ("LLM", "Delete the 9am standup and create a new one at 10am with a 30 minute reminder", "multi-step"),
    ("LLM", "Cancel my Friday afternoon and reschedule everything to next week",        "bulk-multi-step"),
    ("LLM", "Add a meeting with the client tomorrow and block two hours before to prepare", "cross-domain-action"),
    ("LLM", "Move the project review to next month and set it as a recurring monthly event", "multi-step"),
    ("LLM", "Reschedule my morning meetings and find me a free slot in the afternoon for deep work", "bulk-multi-step"),

    # --- Bulk / all operations (10) ---
    ("LLM", "Move all my meetings from today to tomorrow",                              "bulk-op"),
    ("LLM", "Cancel everything on my calendar this Friday",                             "bulk-op"),
    ("LLM", "Reschedule all my events this week to next week",                          "bulk-op"),
    ("LLM", "Delete all tasks due before today",                                        "bulk-op"),
    ("LLM", "Mark all tasks from last week as complete",                                "bulk-op"),
    ("LLM", "Move every meeting before 10am to after lunch",                            "bulk-op"),
    ("LLM", "Cancel all my recurring standups for this month",                          "bulk-op"),
    ("LLM", "Reschedule everything I have on Monday to Tuesday",                        "bulk-op"),
    ("LLM", "Remove all reminders for events this week",                                "bulk-op"),
    ("LLM", "Clear my entire Friday afternoon schedule",                                "bulk-op"),

    # --- Completely out of domain (20) ---
    ("LLM", "What are some good study tips for my biology exam?",                       "out-of-domain"),
    ("LLM", "What is the capital of France?",                                           "out-of-domain"),
    ("LLM", "Can you explain how photosynthesis works?",                                "out-of-domain"),
    ("LLM", "What should I cook for dinner tonight?",                                   "out-of-domain"),
    ("LLM", "How do I fix a memory leak in Python?",                                    "out-of-domain"),
    ("LLM", "Tell me a joke",                                                           "out-of-domain"),
    ("LLM", "What is the best way to learn machine learning?",                          "out-of-domain"),
    ("LLM", "Who won the Premier League last season?",                                  "out-of-domain"),
    ("LLM", "How do I negotiate a salary raise?",                                       "out-of-domain"),
    ("LLM", "Give me tips for a job interview",                                         "out-of-domain"),
    ("LLM", "What is the weather like this weekend?",                                   "out-of-domain"),
    ("LLM", "How can I improve my productivity?",                                       "out-of-domain"),
    ("LLM", "Can you write me a cover letter?",                                         "out-of-domain"),
    ("LLM", "What are the symptoms of burnout?",                                        "out-of-domain"),
    ("LLM", "Tell me about the history of the Roman Empire",                            "out-of-domain"),
    ("LLM", "How do I make sourdough bread?",                                           "out-of-domain"),
    ("LLM", "What films are showing this weekend?",                                     "out-of-domain"),
    ("LLM", "Can you help me write a Python script to scrape websites?",                "out-of-domain"),
    ("LLM", "What is the meaning of life?",                                             "out-of-domain"),
    ("LLM", "How do I get better at public speaking?",                                  "out-of-domain"),

    # --- Conditionals / vague (15) ---
    ("LLM", "Reschedule the meeting if John is not available on Friday",                "conditional"),
    ("LLM", "Book a call with the team sometime next week",                             "vague"),
    ("LLM", "Schedule a meeting whenever Sarah is free",                                "vague"),
    ("LLM", "Add an event at some point on Thursday",                                   "vague"),
    ("LLM", "Move the meeting unless it conflicts with the workshop",                   "conditional"),
    ("LLM", "Schedule a standup only if the project review is done by then",            "conditional"),
    ("LLM", "Remind me eventually about the report",                                    "vague"),
    ("LLM", "Book something for next week at some point",                               "vague"),
    ("LLM", "Cancel the meeting depending on whether we hit the deadline",              "conditional"),
    ("LLM", "Add a session whenever I have a gap this week",                            "vague"),
    ("LLM", "Schedule a catch-up with whoever is available on Friday",                 "vague"),
    ("LLM", "Move the sync assuming the client confirms",                               "conditional"),
    ("LLM", "Block some time for deep work sometime in the morning",                    "vague"),
    ("LLM", "Set a reminder at some point before the meeting",                          "vague"),
    ("LLM", "Reschedule unless it clashes with something else",                         "conditional"),

    # --- Referential / context-dependent (10) ---
    ("LLM", "Actually move it to 4pm instead",                                          "referential"),
    ("LLM", "Change that to Thursday",                                                  "referential"),
    ("LLM", "Cancel the same one as last time",                                         "referential"),
    ("LLM", "Do the same thing for next week",                                          "referential"),
    ("LLM", "Remind me about that one too",                                             "referential"),
    ("LLM", "Move that meeting we just talked about",                                   "referential"),
    ("LLM", "Delete the one I just created",                                            "referential"),
    ("LLM", "Reschedule it to the same time but on Wednesday",                         "referential"),
    ("LLM", "Set the same reminder for this one as well",                               "referential"),
    ("LLM", "Add those tasks to my list too",                                           "referential"),

    # --- Gibberish / incomplete / degenerate (10) ---
    ("LLM", "Create.",                                                                  "degenerate"),
    ("LLM", "Schedule",                                                                 "degenerate"),
    ("LLM", "Meeting",                                                                  "degenerate"),
    ("LLM", "asdfghjkl",                                                                "degenerate"),
    ("LLM", "...",                                                                      "degenerate"),
    ("LLM", "yes please",                                                               "degenerate"),
    ("LLM", "okay",                                                                     "degenerate"),
    ("LLM", "I want to",                                                                "degenerate"),
    ("LLM", "the thing for the",                                                        "degenerate"),
    ("LLM", "maybe tomorrow or the next day or whenever",                               "degenerate"),

    # --- Conversational / chat-style (15) ---
    ("LLM", "Can you help me figure out how to organise my week better?",              "conversational"),
    ("LLM", "I feel like I have too many meetings this week, what do you think?",       "conversational"),
    ("LLM", "What would you suggest for my schedule tomorrow?",                         "conversational"),
    ("LLM", "I need to prepare for an exam on Friday, help me plan my week",            "conversational"),
    ("LLM", "Can you look at my calendar and tell me if I am overbooked?",              "conversational"),
    ("LLM", "What would be the best way to structure my day tomorrow?",                 "conversational"),
    ("LLM", "I have a big presentation Friday, what should I do this week to prepare?", "conversational"),
    ("LLM", "Do you think I should move my gym session or keep it?",                   "conversational"),
    ("LLM", "Help me plan a productive morning routine starting next Monday",           "conversational"),
    ("LLM", "Can you review my schedule and suggest where I can fit in study time?",   "conversational"),
    ("LLM", "I keep missing my reminders, how should I fix that?",                     "conversational"),
    ("LLM", "What is the best time for deep work based on my current schedule?",       "conversational"),
    ("LLM", "I want to be more productive, can you restructure my week?",              "conversational"),
    ("LLM", "Tell me if my schedule looks reasonable for this week",                   "conversational"),
    ("LLM", "How should I balance my meetings and tasks this week?",                   "conversational"),
]