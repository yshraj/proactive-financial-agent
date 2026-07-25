import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { MessageCircle, X } from "lucide-react";
import { useContact } from "@/contexts/ContactContext";
import { ContactChat } from "./ContactChat";

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea,input,select,[tabindex]:not([tabindex="-1"])';

/**
 * Global floating contact/support widget — mounted once by ContactProvider.
 * Bottom-right chat bubble everywhere in the app (marketing + authenticated
 * shell); other components open it via useContact().openContact(topic).
 */
export function ContactWidget() {
  const { open, topic, openContact, closeContact } = useContact();
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  // Bumped on every open so ContactChat remounts fresh instead of resuming a
  // finished/errored conversation from the last time the widget was open.
  const [sessionKey, setSessionKey] = useState(0);

  useEffect(() => {
    if (open) setSessionKey((k) => k + 1);
  }, [open]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        closeContact();
        return;
      }
      if (e.key === "Tab" && panelRef.current) {
        const nodes = Array.from(
          panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)
        ).filter((n) => n.offsetParent !== null);
        if (nodes.length === 0) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    },
    [closeContact]
  );

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement;
    const prevOverflow = document.body.style.overflow;
    // Only lock page scroll on mobile, where the panel is a full-width sheet;
    // on desktop it's a floating card and the page behind stays usable.
    const isMobile = typeof window !== "undefined" && window.matchMedia("(max-width: 639px)").matches;
    if (isMobile) document.body.style.overflow = "hidden";
    const t = window.setTimeout(() => {
      panelRef.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    }, 60);
    return () => {
      window.clearTimeout(t);
      document.body.style.overflow = prevOverflow;
      previouslyFocused.current?.focus?.();
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => (open ? closeContact() : openContact())}
        aria-expanded={open}
        aria-label={open ? "Close contact chat" : "Contact us"}
        data-testid="contact-widget-trigger"
        className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-slate-950 text-white shadow-overlay transition-transform hover:scale-105 active:scale-95"
      >
        {open ? (
          <X className="h-5 w-5" aria-hidden />
        ) : (
          <MessageCircle className="h-5 w-5" aria-hidden />
        )}
      </button>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              key="contact-scrim"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              onClick={closeContact}
              aria-hidden
              className="fixed inset-0 z-40 bg-slate-900/30 sm:bg-transparent"
            />
            <motion.div
              key="contact-panel"
              ref={panelRef}
              role="dialog"
              aria-modal="true"
              aria-label="Contact KritiFin"
              initial={{ opacity: 0, y: 24, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 16, scale: 0.98 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              onClick={(e) => e.stopPropagation()}
              onKeyDown={handleKeyDown}
              className="fixed inset-x-0 bottom-0 z-50 flex max-h-[88vh] w-full flex-col overflow-hidden rounded-t-3xl border border-slate-200 bg-white shadow-overlay sm:inset-x-auto sm:bottom-24 sm:right-6 sm:max-h-[min(640px,80vh)] sm:w-[380px] sm:rounded-3xl"
            >
              <ContactChat key={sessionKey} initialTopic={topic} onClose={closeContact} />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
