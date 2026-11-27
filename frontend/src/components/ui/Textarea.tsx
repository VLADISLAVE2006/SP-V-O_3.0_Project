import React from 'react';

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, helperText, className, id, ...props }, ref) => {
    const textareaId = id || `textarea-${Math.random().toString(36).slice(2)}`;
    return (
      <div className="textarea-field">
        {label && (
          <label htmlFor={textareaId} className="textarea-label">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={textareaId}
          className={`textarea ${error ? 'textarea-error' : ''} ${className ?? ''}`}
          {...props}
          aria-invalid={error ? 'true' : 'false'}
        />
        {error && (
          <p id={`${textareaId}-error`} className="input-error-text">
            {error}
          </p>
        )}
        {!error && helperText && (
          <p id={`${textareaId}-helper`} className="input-helper-text">
            {helperText}
          </p>
        )}
      </div>
    );
  }
);
Textarea.displayName = 'Textarea';