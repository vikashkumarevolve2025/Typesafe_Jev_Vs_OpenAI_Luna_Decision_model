import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LLM Chess Arena",
  description: "Watch Claude, Jev and offline engines play chess — with latency, cost, tokens and the exact data sent per move.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
