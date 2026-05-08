import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "verarel.com",
  description: "High-performance dating platform with compatibility, chat, trust, and date planning.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
