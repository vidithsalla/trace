import type { ReactNode } from "react";

import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Trace",
  description: "Evidence review with version-aware citations, counterevidence and change control. Runs on your own machine.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
