import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, ArrowLeft, CheckCircle2, Send } from "lucide-react";
import { errorMessage } from "@/lib/api";
import {
  CONTACT_TOPICS,
  validateEmail,
  validateMessage,
  validateName,
  type ContactTopic,
} from "@/lib/contact";
import { useSubmitContact } from "@/hooks/useContactApi";

type StepKey = "name" | "email" | "topic" | "message";

interface ChatMessage {
  id: string;
  role: "bot" | "user";
  text: string;
}

const TOPIC_COPY: Record<ContactTopic, { greeting: string; messagePrompt: string }> = {
  sales: {
    greeting: "Interested in KritiFin? Let's get a few details so we can set up a demo.",
    messagePrompt: "Tell me a bit about your team and what you'd like to see in the demo.",
  },
  support: {
    greeting: "Happy to help — let's get some quick details first.",
    messagePrompt: "What can we help with?",
  },
  bug: {
    greeting: "Sorry you hit a snag — let's get this to the right person.",
    messagePrompt: "What went wrong? Include what you were doing when it happened, if you can.",
  },
  general: {
    greeting: "Hi! I'm the KritiFin assistant. Let's get you connected with the team.",
    messagePrompt: "What would you like to tell us?",
  },
};

const nextId = () => Math.random().toString(36).slice(2);

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 rounded-2xl rounded-bl-md bg-slate-100 px-3.5 py-2.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400"
          style={{ animationDelay: `${i * 0.12}s` }}
        />
      ))}
    </span>
  );
}

function Bubble({ role, children }: { role: "bot" | "user"; children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className={`flex ${role === "user" ? "justify-end" : "justify-start"}`}
    >
      <div
        className={
          role === "user"
            ? "max-w-[85%] rounded-2xl rounded-br-md bg-brand-600 px-3.5 py-2.5 text-sm leading-relaxed text-white"
            : "max-w-[85%] rounded-2xl rounded-bl-md bg-slate-100 px-3.5 py-2.5 text-sm leading-relaxed text-slate-700"
        }
      >
        {children}
      </div>
    </motion.div>
  );
}

export function ContactChat({
  initialTopic,
  onClose,
}: {
  initialTopic?: ContactTopic;
  onClose: () => void;
}) {
  const steps = useMemo<StepKey[]>(
    () => (initialTopic ? ["name", "email", "message"] : ["name", "email", "topic", "message"]),
    [initialTopic]
  );
  const [stepIndex, setStepIndex] = useState(0);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [botTyping, setBotTyping] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [topic, setTopic] = useState<ContactTopic | undefined>(initialTopic);
  const [message, setMessage] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const initializedRef = useRef(false);
  const submit = useSubmitContact();

  const currentStep = steps[stepIndex];
  const done = submit.isSuccess;
  const showTyping = botTyping || submit.isPending;

  function askStep(step: StepKey | undefined, topicOverride?: ContactTopic) {
    if (!step) return;
    const activeTopic = topicOverride ?? topic ?? "general";
    const question =
      step === "name"
        ? "First, what's your name?"
        : step === "email"
          ? "Thanks! What's the best email to reach you at?"
          : step === "topic"
            ? "What's this about?"
            : TOPIC_COPY[activeTopic].messagePrompt;
    setBotTyping(true);
    window.setTimeout(
      () => {
        setBotTyping(false);
        setMessages((current) => [...current, { id: nextId(), role: "bot", text: question }]);
        window.setTimeout(() => inputRef.current?.focus(), 30);
      },
      messages.length === 0 ? 500 : 420
    );
  }

  // Greet once on mount, then ask the first question. Guarded against
  // React StrictMode's double-invoked mount effect in development, which
  // would otherwise queue the greeting/first-question twice.
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    setMessages([{ id: nextId(), role: "bot", text: TOPIC_COPY[initialTopic ?? "general"].greeting }]);
    askStep(steps[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [messages, showTyping, submit.isError, done]);

  function pushUser(text: string) {
    setMessages((current) => [...current, { id: nextId(), role: "user", text }]);
  }

  function goToStep(nextIndex: number, topicOverride?: ContactTopic) {
    setFieldError(null);
    setStepIndex(nextIndex);
    if (nextIndex >= steps.length) {
      submitAll(topicOverride);
      return;
    }
    askStep(steps[nextIndex], topicOverride);
  }

  function submitAll(topicOverride?: ContactTopic) {
    submit.mutate({
      name: name.trim(),
      email: email.trim(),
      topic: topicOverride ?? topic ?? "general",
      message: message.trim(),
      website: "",
    });
  }

  function handleBack() {
    if (stepIndex === 0 || showTyping) return;
    setMessages((current) => current.slice(0, Math.max(0, current.length - 2)));
    setFieldError(null);
    setStepIndex((i) => i - 1);
    window.setTimeout(() => inputRef.current?.focus(), 30);
  }

  function handleNameSubmit() {
    const err = validateName(name);
    setFieldError(err);
    if (err) return;
    pushUser(name.trim());
    goToStep(stepIndex + 1);
  }

  function handleEmailSubmit() {
    const err = validateEmail(email);
    setFieldError(err);
    if (err) return;
    pushUser(email.trim());
    goToStep(stepIndex + 1);
  }

  function handleTopicSelect(value: ContactTopic) {
    setTopic(value);
    setFieldError(null);
    pushUser(CONTACT_TOPICS.find((t) => t.value === value)?.label ?? value);
    goToStep(stepIndex + 1, value);
  }

  function handleMessageSubmit() {
    const err = validateMessage(message);
    setFieldError(err);
    if (err) return;
    pushUser(message.trim());
    goToStep(stepIndex + 1);
  }

  const firstName = name.trim().split(/\s+/)[0] || "there";
  const errorId = "contact-field-error";

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="contact-chat">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div>
          <p className="text-sm font-semibold text-slate-950">KritiFin Assistant</p>
          <p className="text-xs text-slate-500">Usually replies within one business day</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          aria-label="Close contact chat"
        >
          ×
        </button>
      </div>

      {!done && (
        <div className="flex gap-1.5 px-5 pt-3" aria-hidden>
          {steps.map((step, i) => (
            <span
              key={step}
              className={`h-1 flex-1 rounded-full transition-colors ${
                i < stepIndex ? "bg-brand-500" : i === stepIndex ? "bg-brand-300" : "bg-slate-100"
              }`}
            />
          ))}
        </div>
      )}

      <div
        ref={transcriptRef}
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto px-5 py-4"
      >
        {messages.map((m) => (
          <Bubble key={m.id} role={m.role}>
            {m.text}
          </Bubble>
        ))}
        {showTyping && (
          <div className="flex justify-start">
            <TypingDots />
          </div>
        )}
        {submit.isError && !submit.isPending && (
          <div className="flex justify-start">
            <div className="max-w-[90%] rounded-2xl rounded-bl-md border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
              <div className="flex items-start gap-2">
                <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
                <p>{errorMessage(submit.error, "Something went wrong sending your message.")}</p>
              </div>
              <button
                type="button"
                onClick={() => submitAll()}
                className="mt-2 text-xs font-semibold text-red-700 underline underline-offset-2"
              >
                Try again
              </button>
            </div>
          </div>
        )}
        {done && (
          <Bubble role="bot">
            <div className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-emerald-600" aria-hidden />
              <span data-testid="contact-success">
                Got it, {firstName}! Thanks — our team will get back to you at {email.trim()}{" "}
                shortly.
              </span>
            </div>
          </Bubble>
        )}
      </div>

      {!done && !showTyping && (
        <div className="border-t border-slate-100 px-5 py-4">
          {currentStep === "name" && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleNameSubmit();
              }}
              noValidate
              className="flex items-end gap-2"
            >
              <div className="flex-1">
                <label htmlFor="contact-name" className="sr-only">
                  Your name
                </label>
                <input
                  id="contact-name"
                  ref={inputRef as React.RefObject<HTMLInputElement>}
                  type="text"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setFieldError(null);
                  }}
                  placeholder="Your name"
                  autoComplete="name"
                  aria-invalid={!!fieldError}
                  aria-describedby={fieldError ? errorId : undefined}
                  data-testid="contact-input"
                  className="input h-11 text-base"
                />
                {fieldError && (
                  <p id={errorId} role="alert" className="mt-1.5 text-xs text-red-600">
                    {fieldError}
                  </p>
                )}
              </div>
              <button
                type="submit"
                aria-label="Send"
                data-testid="contact-send"
                className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white transition-colors hover:bg-brand-500"
              >
                <Send className="h-4 w-4" aria-hidden />
              </button>
            </form>
          )}

          {currentStep === "email" && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleEmailSubmit();
              }}
              noValidate
              className="flex items-end gap-2"
            >
              <div className="flex-1">
                <label htmlFor="contact-email" className="sr-only">
                  Your email
                </label>
                <input
                  id="contact-email"
                  ref={inputRef as React.RefObject<HTMLInputElement>}
                  type="email"
                  inputMode="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setFieldError(null);
                  }}
                  placeholder="you@company.com"
                  autoComplete="email"
                  aria-invalid={!!fieldError}
                  aria-describedby={fieldError ? errorId : undefined}
                  data-testid="contact-input"
                  className="input h-11 text-base"
                />
                {fieldError && (
                  <p id={errorId} role="alert" className="mt-1.5 text-xs text-red-600">
                    {fieldError}
                  </p>
                )}
              </div>
              <button
                type="submit"
                aria-label="Send"
                data-testid="contact-send"
                className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white transition-colors hover:bg-brand-500"
              >
                <Send className="h-4 w-4" aria-hidden />
              </button>
            </form>
          )}

          {currentStep === "topic" && (
            <div className="grid grid-cols-2 gap-2" data-testid="contact-input">
              {CONTACT_TOPICS.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => handleTopicSelect(t.value)}
                  className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-left text-sm font-medium text-slate-700 transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700"
                >
                  {t.label}
                </button>
              ))}
            </div>
          )}

          {currentStep === "message" && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleMessageSubmit();
              }}
              noValidate
              className="flex items-end gap-2"
            >
              <div className="flex-1">
                <label htmlFor="contact-message" className="sr-only">
                  Your message
                </label>
                <textarea
                  id="contact-message"
                  ref={inputRef as React.RefObject<HTMLTextAreaElement>}
                  value={message}
                  onChange={(e) => {
                    setMessage(e.target.value);
                    setFieldError(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleMessageSubmit();
                    }
                  }}
                  placeholder="Type your message… (Enter to send, Shift+Enter for a new line)"
                  rows={3}
                  aria-invalid={!!fieldError}
                  aria-describedby={fieldError ? errorId : undefined}
                  data-testid="contact-input"
                  className="input min-h-[76px] resize-none py-2.5 text-base"
                />
                {fieldError && (
                  <p id={errorId} role="alert" className="mt-1.5 text-xs text-red-600">
                    {fieldError}
                  </p>
                )}
              </div>
              <button
                type="submit"
                aria-label="Send"
                data-testid="contact-send"
                className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white transition-colors hover:bg-brand-500"
              >
                <Send className="h-4 w-4" aria-hidden />
              </button>
            </form>
          )}

          {stepIndex > 0 && (
            <button
              type="button"
              onClick={handleBack}
              className="mt-2.5 inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-700"
            >
              <ArrowLeft className="h-3 w-3" aria-hidden />
              Back
            </button>
          )}
        </div>
      )}

      {done && (
        <div className="border-t border-slate-100 px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="w-full rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-slate-800"
          >
            Done
          </button>
        </div>
      )}
    </div>
  );
}
