import React from 'react';

export type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'secondary';

export interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'badge-default',
  success: 'badge-success',
  warning: 'badge-warning',
  danger: 'badge-danger',
  info: 'badge-info',
  secondary: 'badge-secondary',
};

export const Badge: React.FC<BadgeProps> = ({ variant = 'default', children }) => {
  return <span className={`badge ${variantStyles[variant]}`}>{children}</span>;
};