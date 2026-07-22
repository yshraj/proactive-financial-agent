import type { AppProps } from "next/app";
import { Inter } from "next/font/google";
import { useState } from "react";
import { useRouter } from "next/router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "../styles/globals.css";
import { LayoutProvider } from "../contexts/LayoutContext";
import { AuthProvider, AuthGuard } from "../contexts/AuthContext";
import { CreditProvider } from "../contexts/CreditContext";
import { AccessGate } from "../components/AccessGate";
import AppLayout from "../components/AppLayout";
import { SystemBanners } from "../components/SystemBanners";
import { ErrorBoundary, ToastProvider } from "../components/ui";
import { BARE_ROUTES } from "../lib/routes";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter();
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
            // Recover automatically when connectivity returns (pairs with the
            // offline banner in SystemBanners).
            refetchOnReconnect: true,
            staleTime: 30_000,
            gcTime: 5 * 60_000,
          },
        },
      })
  );

  // Marketing/auth routes render full-bleed, without the authenticated app
  // shell (sidebar + header). Everything else gets the dashboard chrome.
  const isBare = BARE_ROUTES.has(router.pathname);

  const page = (
    <ErrorBoundary>
      <Component {...pageProps} />
    </ErrorBoundary>
  );

  return (
    <div className={`${inter.variable} font-sans`}>
      <QueryClientProvider client={queryClient}>
        <SystemBanners />
        <ToastProvider>
          <AuthProvider>
            <LayoutProvider>
              {isBare ? (
                page
              ) : (
                <AccessGate>
                  <AuthGuard>
                    <CreditProvider>
                      <AppLayout>{page}</AppLayout>
                    </CreditProvider>
                  </AuthGuard>
                </AccessGate>
              )}
            </LayoutProvider>
          </AuthProvider>
        </ToastProvider>
      </QueryClientProvider>
    </div>
  );
}
