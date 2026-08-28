import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000'),
  title: 'Game Trainer · Poker',
  description: 'Practice heads-up no-limit hold’em against an explainable strategy engine.',
  openGraph: {
    title: 'Game Trainer',
    description: 'Learn the decision, not just the answer.',
    images: [{ url: '/og.png', width: 1792, height: 934, alt: 'Game Trainer poker strategy coach' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Game Trainer',
    description: 'Learn the decision, not just the answer.',
    images: ['/og.png'],
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
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
