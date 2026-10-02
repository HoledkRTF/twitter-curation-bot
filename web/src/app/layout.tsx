import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Curation Web Player',
  description: 'Full-screen continuous media curation player',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-black text-white select-none">{children}</body>
    </html>
  );
}
