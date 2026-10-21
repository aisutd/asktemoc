import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Navbar from "@/components/navbar";
import { AuthSessionProvider } from "@/components/session-provider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Ask Temoc - Your AI Guide to UTD",
  description:
    "Get instant answers about UTD classes, campus life, resources, and everything university-related. Powered by AI, Temoc is your 24/7 UTD assistant.",
  icons: {
    icon: "/temochead.svg",
    shortcut: "/temochead.svg",
    apple: "/temochead.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} flex h-dvh flex-col overflow-hidden antialiased`}
      >
        <AuthSessionProvider>
          <Navbar />
          <div className="flex min-h-0 flex-1 flex-col overflow-auto">{children}</div>
        </AuthSessionProvider>
      </body>
    </html>
  );
}
