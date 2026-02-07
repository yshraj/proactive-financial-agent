import type { AppProps } from "next/app";
import { Inter } from "next/font/google";
import "../styles/globals.css";
import { LayoutProvider } from "../contexts/LayoutContext";
import AppLayout from "../components/AppLayout";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export default function App({ Component, pageProps }: AppProps) {
  return (
    <div className={`${inter.variable} font-sans`}>
      <LayoutProvider>
        <AppLayout>
          <Component {...pageProps} />
        </AppLayout>
      </LayoutProvider>
    </div>
  );
}
