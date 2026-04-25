export interface LinkedAccount {
  provider: string;
  email: string;
  refresh_token?: string;
}




export interface CalendarEvent {
  id: string;
  title: string;
  
  // Active Timestamps
  start: string; 
  end: string;   
  
  // Baseline & Sync
  original_start: string; 
  original_end: string;
  proposed_start: string | null; 
  proposed_end: string | null;
  previous_start: string | null; 
  previous_end: string | null;

  // Metadata
  provider: "google" | "outlook" | "custom";
  email: string;
  location: string | null;
  meeting_link: string | null;
  description: string | null;
  status: "synced" | "drifted" | "conflict" | "resolved";
  
  // AI & Logic Constraints
  is_locked: boolean;      
  has_drifted: boolean;    
  requires_review: boolean; 
  sync_action_required?: "none" | "push_to_provider" | "pull_from_provider";

  // Travel Tracking
  travel_time: number; 
  travel_origin: string | null;
  travel_mode: "driving" | "transit" | "walking" | "cycling";

  // Recurrence & Exceptions
  recurrence: "none" | "daily" | "weekly" | "monthly" | "custom";
  recurrence_days: string[]; 
  exception_dates: string[]; 
  parent_event_id?: string;  

  // Resources
  attachments: string[];
  category?: string;

  // --- NEW TELEMETRY & HABIT FIELDS ---
  completion_status?: "pending" | "completed" | "missed";
  snooze_count?: number;
  completed_at?: string | null;
  debt_applied?: boolean;
  is_perishable?: boolean;
  is_ghost?: boolean;
}