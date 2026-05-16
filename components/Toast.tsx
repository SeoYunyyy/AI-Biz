'use client';

import { useEffect, useState } from 'react';

interface Props {
  message: string | null;
  type?: 'success' | 'error' | 'info';
  onDismiss: () => void;
}

export function Toast({ message, type = 'success', onDismiss }: Props) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (message) {
      setVisible(true);
      const t = setTimeout(() => {
        setVisible(false);
        setTimeout(onDismiss, 300);
      }, 3000);
      return () => clearTimeout(t);
    }
  }, [message, onDismiss]);

  if (!message) return null;

  const bg =
    type === 'success'
      ? 'bg-gray-900'
      : type === 'error'
      ? 'bg-red-500'
      : 'bg-indigo-500';

  return (
    <div
      className={`fixed top-14 left-1/2 -translate-x-1/2 z-50 px-4 py-2.5 rounded-2xl shadow-lg text-white text-sm font-medium transition-all duration-300 max-w-[85vw] text-center ${bg} ${
        visible ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-2'
      }`}
    >
      {message}
    </div>
  );
}
