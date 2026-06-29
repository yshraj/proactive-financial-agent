import { useCallback, useState } from "react";
import type { DraftEmailSource } from "@/lib/types";

/** Shared draft-email modal open/close state used across dashboard, alerts, brief, and client pages. */
export function useDraftEmailModalState() {
  const [source, setSource] = useState<DraftEmailSource | null>(null);

  const openAlertDraft = useCallback((alertId: string) => {
    setSource({ type: "alert", alertId });
  }, []);

  const openBriefDraft = useCallback(
    (clientId: string, context: string, talkingPoints?: string[]) => {
      setSource({ type: "brief", clientId, context, talkingPoints });
    },
    []
  );

  const closeDraft = useCallback(() => setSource(null), []);

  return {
    source,
    openAlertDraft,
    openBriefDraft,
    closeDraft,
  };
}
