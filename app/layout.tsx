import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "synkore·拓境",
  description: "把课堂听清楚，把知识讲明白。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">{children}</body>
    </html>
  );
}
