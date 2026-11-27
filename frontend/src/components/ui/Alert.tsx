import React from 'react';

export type AlertVariant = 'success' | 'error' | 'warning' | 'info';

export interface AlertProps {
  variant?: AlertVariant;
  title?: string;
  children: React.ReactNode;
}

const variantStyles: Record<AlertVariant, string> = {
  success: 'alert-success',
  error: 'alert-error',
  warning: 'alert-warning',
  info: 'alert-info',
};

export const Alert: React.FC<AlertProps> = ({ variant = 'info', title, children }) => {
  return (
    <div className={`alert ${variantStyles[variant]}`}>
      {title && <strong className="alert-title">{title}</strong>}
      <span className="alert-message">{children}</span>
    </div>
  );
};