import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GovAssist",
  description:
    "Check government scheme eligibility, with the exact rule quoted from the official document.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
