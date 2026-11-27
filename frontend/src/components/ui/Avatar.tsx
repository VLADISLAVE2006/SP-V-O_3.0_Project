import React from 'react';

export interface AvatarProps {
  src?: string | null;
  alt?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const Avatar: React.FC<AvatarProps> = ({ src, alt, size = 'md', className }) => {
  const initials = alt ? alt.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2) : '?';

  return (
    <div
      className={`avatar avatar-${size} ${className ?? ''}`}
      aria-label={alt || 'Avatar'}
    >
      {src ? (
        <img src={src} alt={alt ?? 'Avatar'} className="avatar-img" />
      ) : (
        <span className="avatar-initials">{initials}</span>
      )}
    </div>
  );
};