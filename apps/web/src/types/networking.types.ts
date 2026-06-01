export type ContactStatus = "to_reach" | "contacted" | "responded" | "connected";

export interface Contact {
  id: string;
  name: string;
  role: string;
  company: string;
  status: ContactStatus;
  /** Why this person is a useful connection for the user's goal. */
  reason?: string;
  lastTouchLabel?: string;
}

export interface NetworkingEvent {
  id: string;
  title: string;
  kind: "meetup" | "conference" | "webinar" | "ama";
  dateLabel: string;
  location: string;
  isOnline: boolean;
}

export interface OutreachEntry {
  id: string;
  contactName: string;
  channel: "email" | "linkedin" | "in_person" | "other";
  note: string;
  timeLabel: string;
}
