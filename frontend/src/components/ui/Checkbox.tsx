import React from 'react';

export interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ label, error, className, id, ...props }, ref) => {
    const checkboxId = id || `checkbox-${Math.random().toString(36).slice(2)}`;
    return (
      <div className={`checkbox-field ${error ? 'checkbox-error' : ''} ${className ?? ''}`}>
        <input
          ref={ref}
          id={checkboxId}
          type="checkbox"
          className="checkbox-input"
          {...props}
          aria-invalid={error ? 'true' : 'false'}
        />
        {label && (
          <label htmlFor={checkboxId} className="checkbox-label">
            {label}
          </label>
        )}
        {error && (
          <span className="input-error-text">{error}</span>
        )}
      </div>
    );
  }
);
Checkbox.displayName = 'Checkbox';