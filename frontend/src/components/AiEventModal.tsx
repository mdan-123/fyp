// "use client";

// import { useState, useEffect, useRef } from "react";

// interface AiEventModalProps {
//   isOpen: boolean;
//   onClose: () => void;
//   userId: string;
//   onSaveSuccess: () => void;
// }

// const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

// export default function AiEventModal({ isOpen, onClose, userId, onSaveSuccess }: AiEventModalProps) {
//   const [step, setStep] = useState<'input' | 'processing' | 'review'>('input');
//   const [inputType, setInputType] = useState<'voice' | 'text'>('voice');
//   const [inputText, setInputText] = useState("");
//   const [isRecording, setIsRecording] = useState(false);
//   const [parsedEvent, setParsedEvent] = useState<any>(null);
  
//   const recognitionRef = useRef<any>(null);

//   useEffect(() => {
//     const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
//     if (SpeechRecognition) {
//       recognitionRef.current = new SpeechRecognition();
      
//       // Setting continuous to true stops it from timing out when you take a breath
//       recognitionRef.current.continuous = true;
//       recognitionRef.current.interimResults = true;
      
//       recognitionRef.current.onresult = (event: any) => {
//         let currentTranscript = "";
//         for (let i = 0; i < event.results.length; i++) {
//           currentTranscript += event.results[i][0].transcript;
//         }
//         setInputText(currentTranscript);
//       };

//       recognitionRef.current.onerror = (event: any) => {
//         console.error("Speech recognition error", event.error);
//         setIsRecording(false);
//       };
//     }
    
//     return () => {
//       if (recognitionRef.current) {
//         recognitionRef.current.abort();
//       }
//     };
//   }, []);

//   if (!isOpen) return null;

//   const toggleRecording = () => {
//     if (isRecording) {
//       recognitionRef.current?.stop();
//       setIsRecording(false);
//     } else {
//       setInputText("");
//       recognitionRef.current?.start();
//       setIsRecording(true);
//     }
//   };

//   const processWithAi = async () => {
//     if (!inputText.trim()) return;
    
//     if (isRecording) {
//       recognitionRef.current?.stop();
//       setIsRecording(false);
//     }

//     setStep('processing');
    
//     try {
//       const res = await fetch(`${API_BASE_URL}/api/ai/parse`, {
//         method: 'POST',
//         headers: { 'Content-Type': 'application/json' },
//         body: JSON.stringify({
//           text: inputText,
//           user_id: userId,
//           timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
//         })
//       });
      
//       const data = await res.json();
//       console.log("AI Parse Response:", data);
      
//       if (data.status === 'success') {
//         // We assume your python API returns the drafted event in data.event
//         setParsedEvent(data.event);
//         setStep('review');
//       } else {
//         throw new Error("AI failed to parse");
//       }
//     } catch (err) {
//       console.error("AI Parse Error:", err);
//       alert("The AI couldn't quite understand that. Please try rephrasing.");
//       setStep('input');
//     }
//   };

//   const handleConfirmAndSave = async () => {
//     setStep('processing');
//     try {
//       // Send the reviewed data to your local staging database
//       const res = await fetch(`${API_BASE_URL}/api/calendar/save-local`, {
//         method: "POST",
//         headers: { "Content-Type": "application/json" },
//         body: JSON.stringify({
//           ...parsedEvent,
//           user_id: userId,
//           sync_status: "pending"
//         })
//       });

//       const data = await res.json();
//       if (data.status === "success") {
//         onSaveSuccess();
//         handleClose();
//       } else {
//         throw new Error("Failed to save locally");
//       }
//     } catch (err) {
//       console.error("Save error:", err);
//       alert("Could not save the item. Please try again.");
//       setStep('review');
//     }
//   };

//   const handleClose = () => {
//     setStep('input');
//     setInputText("");
//     setIsRecording(false);
//     setParsedEvent(null);
//     onClose();
//   };

//   return (
//     <div className="fixed inset-0 z-50 flex items-end justify-center bg-gray-900/40 sm:items-center">
//       <div className="w-full h-[65vh] sm:h-auto sm:max-h-[80vh] max-w-lg bg-gray-50 rounded-t-2xl sm:rounded-2xl shadow-xl flex flex-col overflow-hidden">
        
//         <div className="bg-white px-4 py-3 flex justify-between items-center border-b border-gray-100">
//           <h3 className="text-gray-800 font-medium">Add Event with AI</h3>
//           <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 text-2xl leading-none">&times;</button>
//         </div>

//         <div className="p-6 flex-1 flex flex-col overflow-y-auto">
//           {step === 'input' && (
//             <div className="flex flex-col h-full">
//               <div className="flex bg-gray-200/60 p-1 rounded-lg self-center mb-6">
//                 <button 
//                   className={`px-6 py-1.5 text-sm font-medium rounded-md transition-colors ${inputType === 'voice' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
//                   onClick={() => setInputType('voice')}
//                 >
//                   Voice
//                 </button>
//                 <button 
//                   className={`px-6 py-1.5 text-sm font-medium rounded-md transition-colors ${inputType === 'text' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
//                   onClick={() => setInputType('text')}
//                 >
//                   Text
//                 </button>
//               </div>

//               {inputType === 'voice' ? (
//                 <div className="flex-1 flex flex-col space-y-6">
//                   <div className="flex-1 bg-white rounded-xl border border-gray-200 p-4 shadow-sm min-h-[120px]">
//                     <p className={`text-lg ${inputText ? 'text-gray-800' : 'text-gray-400'}`}>
//                       {inputText || "Your words will appear here as you speak..."}
//                     </p>
//                   </div>
                  
//                   <div className="flex flex-col gap-3 mt-auto">
//                     <button 
//                       onClick={toggleRecording}
//                       className={`w-full py-4 rounded-xl font-medium text-white transition-all shadow-sm ${
//                         isRecording ? 'bg-red-500 hover:bg-red-600' : 'bg-indigo-600 hover:bg-indigo-700'
//                       }`}
//                     >
//                       {isRecording ? "Stop Listening" : "Ready to Speak"}
//                     </button>
                    
//                     {inputText && !isRecording && (
//                       <button 
//                         onClick={processWithAi}
//                         className="w-full py-4 bg-gray-900 text-white font-medium rounded-xl hover:bg-gray-800 transition-colors shadow-sm"
//                       >
//                         Process Request
//                       </button>
//                     )}
//                   </div>
//                 </div>
//               ) : (
//                 <div className="flex-1 flex flex-col space-y-4">
//                   <textarea 
//                     value={inputText}
//                     onChange={(e) => setInputText(e.target.value)}
//                     placeholder="e.g., Schedule a study session for tomorrow at 2 PM..."
//                     className="w-full flex-1 rounded-xl border border-gray-200 p-4 text-gray-800 focus:ring-indigo-500 focus:border-indigo-500 resize-none bg-white shadow-sm text-lg"
//                     autoFocus
//                     spellCheck={false}
//                   />
//                   <button 
//                     onClick={processWithAi}
//                     disabled={!inputText.trim()}
//                     className="w-full py-4 bg-indigo-600 text-white font-medium rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-sm"
//                   >
//                     Process Request
//                   </button>
//                 </div>
//               )}
//             </div>
//           )}

//           {step === 'processing' && (
//             <div className="flex-1 flex flex-col items-center justify-center space-y-4">
//               <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin"></div>
//               <p className="text-gray-600 font-medium">Analysing your request...</p>
//             </div>
//           )}

//           {step === 'review' && parsedEvent && (
//             <div className="flex flex-col h-full justify-between space-y-6">
//                 <div>
//                 <p className="text-sm text-gray-500 uppercase tracking-wider mb-4 text-center">Review your event</p>
//                 <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm space-y-3">
//                     {/* RoBERTa puts the event name in an array called 'events' */}
//                     <h4 className="text-xl text-gray-900 font-medium capitalize">
//                     {parsedEvent.entities.events[0] || "New Event"}
//                     </h4>
//                     <div className="text-gray-600 text-sm space-y-2">
//                     <div className="flex items-center gap-2">
//                         <span>📅</span>
//                         <p>Starts: {new Date(parsedEvent.entities.start_timestamp).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}</p>
//                     </div>
//                     <div className="flex items-center gap-2">
//                         <span>🏁</span>
//                         <p>Ends: {new Date(parsedEvent.entities.end_timestamp).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}</p>
//                     </div>
//                     {parsedEvent.entities.locations.length > 0 && (
//                         <div className="flex items-center gap-2">
//                         <span>📍</span>
//                         <p>Location: {parsedEvent.entities.locations[0]}</p>
//                         </div>
//                     )}
//                     </div>
//                 </div>
//                 </div>

//                 <div className="space-y-3 mt-auto">
//                 <button 
//                     onClick={handleConfirmAndSave}
//                     className="w-full py-3.5 bg-indigo-600 text-white text-lg font-medium rounded-xl hover:bg-indigo-700 transition-colors shadow-sm"
//                 >
//                     Confirm & Save
//                 </button>
//                 <button 
//                     onClick={() => setStep('input')}
//                     className="w-full py-3.5 bg-white text-gray-700 border border-gray-200 font-medium rounded-xl hover:bg-gray-50 transition-colors text-sm"
//                 >
//                     Edit or Re-speak
//                 </button>
//                 </div>
//             </div>
//             )}
//         </div>
//       </div>
//     </div>
//   );
// }