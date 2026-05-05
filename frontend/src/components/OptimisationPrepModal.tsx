"use client";

import { useRouter } from "next/navigation";

type Preference = { id: string; raw_input?: string; category: string; reasoning: string; };

interface OptimisationPrepModalProps {
  isOpen: boolean;
  onClose: () => void;
  preferencesCount: number;
  preferences?: Preference[];
  onContinue: (useGenerics?: boolean) => void;
}

export default function OptimisationPrepModal({ 
  isOpen, 
  onClose, 
  preferencesCount,
  preferences = [],
  onContinue 
}: OptimisationPrepModalProps) {
  const router = useRouter();

  const showUserPreferences = preferencesCount >= 3;

  const genericPreferences = [
    { label: "Protect 1 hour for lunch daily", color: 'var(--color-warning)', icon: (
      <svg className="w-4 h-4" style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    )},
    { label: "Keep a 15-min buffer between meetings", color: 'var(--color-info)', icon: (
      <svg className="w-4 h-4" style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
      </svg>
    )},
    { label: "Schedule Deep Work in the mornings", color: 'var(--color-accent-primary)', icon: (
      <svg className="w-4 h-4" style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
      </svg>
    )},
  ];

  const displayedPreferences = showUserPreferences
    ? preferences.slice(0, 5)
    : genericPreferences;

  if (!isOpen) return null;

  const handleGoToSettings = () => {
    onClose();
    router.push('/settings'); 
  };

  return (
    <div 
      className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center p-0 sm:p-4 font-sans animate-fadeIn transition-colors duration-500"
      style={{
        background: 'rgba(0, 0, 0, 0.6)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
      }}
    >
      <div 
        className="w-full max-w-md rounded-t-3xl sm:rounded-2xl flex flex-col overflow-hidden animate-fadeInUp transition-colors duration-500"
        style={{
          background: 'var(--color-bg-glass-strong)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          boxShadow: 'var(--shadow-xl), var(--shadow-inner-glow)',
          border: '1px solid var(--color-border)',
        }}
      >
        
        {/* Header */}
        <div 
          className="px-6 py-5 flex justify-between items-center transition-colors duration-500"
          style={{ borderBottom: '1px solid var(--color-border)' }}
        >
          <button onClick={onClose} className="text-sm font-medium transition-colors hover:opacity-80" style={{ color: 'var(--color-text-secondary)' }}>Cancel</button>
          <span className="text-sm font-semibold transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Optimisation Prep</span>
          <div className="w-10"></div> {/* Spacer for centering */}
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-6">
          <div className="space-y-6 animate-fadeIn">
            <div className="space-y-3 text-center">
              <div 
                className="w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-2 transition-colors duration-500"
                style={{
                  background: 'var(--color-accent-gradient)',
                  boxShadow: 'var(--shadow-glow)',
                }}
              >
                <svg className="w-6 h-6" style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.53 16.122a3 3 0 00-5.78 1.128 2.25 2.25 0 01-2.4 2.245 4.5 4.5 0 008.4-2.245c0-.399-.078-.78-.22-1.128zm0 0a15.998 15.998 0 003.388-1.62m-5.043-.025a15.994 15.994 0 011.622-3.395m3.42 3.42a15.995 15.995 0 004.764-4.648l3.876-5.814a1.151 1.151 0 00-1.597-1.597L14.146 6.32a15.996 15.996 0 00-4.649 4.763m3.42 3.42a6.776 6.776 0 00-3.42-3.42" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold tracking-tight transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>{showUserPreferences ? 'Your Optimisation Rules' : 'Set Your Ground Rules'}</h3>
              <p className="text-sm leading-relaxed transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
                {showUserPreferences
                  ? <>You have <strong className="transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>{preferencesCount}</strong> preference{preferencesCount === 1 ? '' : 's'} set. The AI will use these rules to optimise your schedule.</>
                  : <>You currently have <strong className="transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>{preferencesCount}</strong> preference{preferencesCount === 1 ? '' : 's'} set. Our AI works best with a strong baseline of rules. Would you like to add these standard constraints before optimising?</>}
              </p>
            </div>

            <div 
              className="space-y-3 p-4 rounded-xl transition-colors duration-500"
              style={{
                background: 'var(--color-bg-subtle)',
                border: '1px solid var(--color-border)',
              }}
            >
              {showUserPreferences ? (
                (displayedPreferences as Preference[]).map((pref) => (
                  <div key={pref.id} className="flex items-center gap-3">
                    <div 
                      className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors duration-500"
                      style={{
                        background: 'var(--color-accent-primary)',
                        boxShadow: 'var(--shadow-sm)',
                      }}
                    >
                      <svg className="w-4 h-4" style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                    <p className="text-sm font-medium transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>{pref.raw_input || pref.reasoning}</p>
                  </div>
                ))
              ) : (
                (genericPreferences).map((pref, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <div 
                      className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors duration-500"
                      style={{
                        background: pref.color,
                        boxShadow: 'var(--shadow-sm)',
                      }}
                    >
                      {pref.icon}
                    </div>
                    <p className="text-sm font-medium transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>{pref.label}</p>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="space-y-3 pt-2">
            {!showUserPreferences && (
              <button 
                onClick={() => onContinue(true)}
                className="w-full py-3 px-4 text-sm font-semibold rounded-xl transition-all active:scale-[0.98] btn-primary"
              >
                Add these & Optimise
              </button>
            )}
            <button 
              onClick={() => onContinue(false)}
              className={`w-full py-3 px-4 text-sm font-semibold rounded-xl transition-all active:scale-[0.98] ${showUserPreferences ? 'btn-primary' : 'btn-secondary'}`}
            >
              {showUserPreferences ? 'Optimise' : 'Optimise with current settings'}
            </button>
            <button 
              onClick={handleGoToSettings}
              className="w-full py-2 text-sm font-medium transition-colors hover:opacity-80"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              Customise manually in Settings
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}