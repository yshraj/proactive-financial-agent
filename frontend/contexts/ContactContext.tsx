import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { ContactWidget } from "@/components/contact/ContactWidget";
import type { ContactTopic } from "@/lib/contact";

interface ContactContextValue {
  open: boolean;
  topic: ContactTopic | undefined;
  /** Opens the widget. Pass a topic to skip straight past the "what's this
   * about?" question (e.g. a "Book a demo" CTA already knows the answer). */
  openContact: (topic?: ContactTopic) => void;
  closeContact: () => void;
}

const ContactContext = createContext<ContactContextValue | null>(null);

export function ContactProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [topic, setTopic] = useState<ContactTopic | undefined>(undefined);

  const openContact = useCallback((nextTopic?: ContactTopic) => {
    setTopic(nextTopic);
    setOpen(true);
  }, []);
  const closeContact = useCallback(() => setOpen(false), []);

  const value = useMemo<ContactContextValue>(
    () => ({ open, topic, openContact, closeContact }),
    [open, topic, openContact, closeContact]
  );

  return (
    <ContactContext.Provider value={value}>
      {children}
      <ContactWidget />
    </ContactContext.Provider>
  );
}

export function useContact() {
  const ctx = useContext(ContactContext);
  if (!ctx) throw new Error("useContact must be used within ContactProvider");
  return ctx;
}
