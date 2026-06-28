import type { AppProps } from "next/app";
import { Inter } from "next/font/google";
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "../styles/globals.css";
import { LayoutProvider } from "../contexts/LayoutContext";
import AppLayout from "../components/AppLayout";
import { ErrorBoundary, ToastProvider } from "../components/ui";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export default function App({ Component, pageProps }: AppProps) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
            staleTime: 30_000,
          },
        },
      })
  );

  return (
    <div className={`${inter.variable} font-sans`}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <LayoutProvider>
            <AppLayout>
              <ErrorBoundary>
                <Component {...pageProps} />
              </ErrorBoundary>
            </AppLayout>
          </LayoutProvider>
        </ToastProvider>
      </QueryClientProvider>
    </div>
  );
}
