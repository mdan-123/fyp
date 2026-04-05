import { useState, useCallback, useRef } from 'react';
import { Capacitor } from '@capacitor/core';
import { SpeechRecognition } from '@capgo/capacitor-speech-recognition'; // <-- Updated Import!

export function useSpeech() {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const recognitionRef = useRef<any>(null);

  const startListening = useCallback(async () => {
    setTranscript('');

    if (Capacitor.isNativePlatform()) {
      // --- NATIVE iOS/ANDROID ENGINE ---
      try {
        const { speechRecognition } = await SpeechRecognition.checkPermissions();
        if (speechRecognition !== 'granted') {
          await SpeechRecognition.requestPermissions();
        }
        
        await SpeechRecognition.start({
          language: 'en-GB',
          maxResults: 1,
          prompt: 'Speak now...',
          partialResults: true,
          popup: false,
        });

        setIsListening(true);

        // Listen for live transcription updates
        SpeechRecognition.addListener('partialResults', (data: any) => {
          if (data.matches && data.matches.length > 0) {
            setTranscript(data.matches[0]);
          }
        });
      } catch (err) {
        console.error('Native speech recognition failed:', err);
        setIsListening(false);
      }
    } else {
      // --- DESKTOP WEB ENGINE ---
      const SpeechRecognitionAPI = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      
      if (!SpeechRecognitionAPI) {
        alert('Speech recognition is not supported in this browser. Try Chrome or Safari.');
        return;
      }

      const recognition = new SpeechRecognitionAPI();
      recognitionRef.current = recognition;
      recognition.lang = 'en-GB';
      recognition.continuous = true;
      recognition.interimResults = true;

      recognition.onstart = () => setIsListening(true);
      
      recognition.onresult = (event: any) => {
        let currentTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          currentTranscript += event.results[i][0].transcript;
        }
        setTranscript(currentTranscript);
      };

      recognition.onerror = (event: any) => {
        console.error('Web Speech API Error:', event.error);
        setIsListening(false);
      };

      recognition.onend = () => setIsListening(false);

      recognition.start();
    }
  }, []);

  const stopListening = useCallback(async () => {
    if (Capacitor.isNativePlatform()) {
      try {
        await SpeechRecognition.stop();
        setIsListening(false);
      } catch (err) {
        console.error(err);
      }
    } else {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
        setIsListening(false);
      }
    }
  }, []);

  return { isListening, transcript, startListening, stopListening, setTranscript };
}