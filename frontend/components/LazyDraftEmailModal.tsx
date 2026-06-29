import dynamic from "next/dynamic";
import type { ComponentProps } from "react";

const DraftEmailModal = dynamic(() => import("./DraftEmailModal"), {
  ssr: false,
  loading: () => null,
});

/** Code-split draft email modal — only loaded when a page renders it. */
export default function LazyDraftEmailModal(props: ComponentProps<typeof DraftEmailModal>) {
  return <DraftEmailModal {...props} />;
}
