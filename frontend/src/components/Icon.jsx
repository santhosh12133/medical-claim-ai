// Small stroke icons drawn for this app (24×24 grid, 1.75 stroke). Decorative: hidden from screen readers.
const PATHS = {
  overview: 'M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z',
  submit: 'M12 15V4M7.5 8.5 12 4l4.5 4.5M5 15v4.5h14V15',
  claims: 'M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3',
  assistant: 'M20 11.5a7.5 7.5 0 0 1-10.9 6.7L4.5 19.5l1.3-4.2A7.5 7.5 0 1 1 20 11.5zM9.8 9.6a2.3 2.3 0 0 1 4.4.9c0 1.5-2.2 1.9-2.2 3.1M12 16.3v.1',
  queue: 'M4 13.5 6.6 5h10.8L20 13.5M4 13.5V19h16v-5.5M4 13.5h5l1.2 2h3.6l1.2-2h5',
  table: 'M4 5h16v14H4zM4 10h16M10 10v9',
  policies: 'M12 3.5 19 6v5.6c0 4.3-2.9 7.6-7 8.9-4.1-1.3-7-4.6-7-8.9V6zM9 12l2 2 4-4',
  signout: 'M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10',
  search: 'M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM20 20l-4.8-4.8',
  file: 'M7 3h7l5 5v13H7zM14 3v5h5',
  check: 'M5 12.5 10 17 19 7.5',
  alert: 'M12 4 21 19.5H3zM12 10v4.2M12 16.8v.1',
  chevron: 'M9 6l6 6-6 6',
  close: 'M6 6l12 12M18 6 6 18',
  refresh: 'M19.5 9A8 8 0 0 0 5 7.3M4.5 15A8 8 0 0 0 19 16.7M19.5 4.5V9H15M4.5 19.5V15H9',
  plus: 'M12 5v14M5 12h14',
};

export function Icon({ name, size = 18, className = '' }) {
  return (
    <svg className={`icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} />
    </svg>
  );
}

export function BrandMark({ size = 30 }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect x="1" y="1" width="30" height="30" rx="8" fill="currentColor" />
      <path d="M13 8h6v5h5v6h-5v5h-6v-5H8v-6h5z" fill="#fff" />
      <path d="M12.5 16.2l2.3 2.3 4.7-4.9" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round"
        strokeLinejoin="round" />
    </svg>
  );
}
