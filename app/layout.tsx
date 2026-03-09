import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "iPhone Price Checker",
  description: "Cek harga wajar iPhone second dari @cherishcomapple",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0a0a0a",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body className="min-h-screen">
        <nav className="sticky top-0 z-10 bg-[#0a0a0a]/80 backdrop-blur border-b border-[#1a1a1a]">
          <div className="max-w-lg mx-auto px-4 py-3 flex items-center justify-between">
            <span className="font-semibold text-sm">📱 iPhone Checker</span>
            <a href="/dashboard" className="text-xs text-[#737373] hover:text-white transition-colors">
              Dashboard →
            </a>
          </div>
        </nav>
        <main className="max-w-lg mx-auto px-4 py-6">
          {children}
        </main>
      </body>
    </html>
  );
}
