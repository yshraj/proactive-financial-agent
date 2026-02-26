import type { AppProps } from "next/app";
import { Inter } from "next/font/google";
import { useEffect, useState } from "react";
import "../styles/globals.css";
import { LayoutProvider } from "../contexts/LayoutContext";
import AppLayout from "../components/AppLayout";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function App({ Component, pageProps }: AppProps) {
  const [showBackendWarning, setShowBackendWarning] = useState(false);

  useEffect(() => {
    checkBackendHealth();
  }, []);

  const checkBackendHealth = async () => {
    const startTime = Date.now();
    let warningTimeout: NodeJS.Timeout;

    // Show warning if backend takes more than 5 seconds
    warningTimeout = setTimeout(() => {
      const elapsed = Date.now() - startTime;
      if (elapsed >= 5000) {
        setShowBackendWarning(true);
      }
    }, 5000);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout

      await fetch(`${API_URL}/health`, {
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      clearTimeout(warningTimeout);

      // Auto-hide warning after 8 seconds if it was shown
      if (showBackendWarning) {
        setTimeout(() => {
          setShowBackendWarning(false);
        }, 8000);
      }
    } catch (error) {
      clearTimeout(warningTimeout);
      console.error("Backend health check failed:", error);
    }
  };

  return (
    <div className={`${inter.variable} font-sans`}>
      {/* Backend Warning Toast */}
      {showBackendWarning && (
        <div className="fixed top-4 right-4 z-50 bg-amber-50 border border-amber-200 rounded-lg shadow-lg p-4 max-w-md animate-fade-in">
          <div className="flex items-start gap-3">
            <div className="text-2xl">⏳</div>
            <div className="flex-1">
              <h3 className="font-semibold text-amber-900 mb-1">
                Backend is waking up
              </h3>
              <p className="text-sm text-amber-800">
                The free Render instance may take 30-60 seconds to start. Please wait...
              </p>
            </div>
            <button
              onClick={() => setShowBackendWarning(false)}
              className="text-amber-600 hover:text-amber-800 font-bold text-xl leading-none"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>
      )}

      <LayoutProvider>
        <AppLayout>
          <Component {...pageProps} />
        </AppLayout>
      </LayoutProvider>
    </div>
  );
}
