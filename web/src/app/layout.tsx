import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Curation Web Player',
  description: 'Full-screen continuous media curation player',
  referrer: 'no-referrer',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta name="referrer" content="no-referrer" />
      </head>
      <body className="bg-black text-white select-none">{children}</body>
    </html>
  );
}
