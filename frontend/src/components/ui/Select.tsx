import React, { useState, useRef, useEffect, useCallback } from 'react';

export interface SelectOption {
  value: string | number;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  helperText?: string;
  options: SelectOption[];
  placeholder?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, helperText, options, placeholder, id, value, onChange }, ref) => {
    const [isOpen, setIsOpen] = useState(false);
    const selectRef = useRef<HTMLDivElement>(null);
    const selectId = id || `select-${Math.random().toString(36).slice(2)}`;

    const handleSelect = useCallback((option: SelectOption) => {
      if (onChange) {
        onChange({ target: { value: option.value } } as React.ChangeEvent<HTMLSelectElement>);
      }
      setIsOpen(false);
    }, [onChange]);

    useEffect(() => {
      const handleClickOutside = (event: MouseEvent) => {
        if (selectRef.current && !selectRef.current.contains(event.target as Node)) {
          setIsOpen(false);
        }
      };
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    return (
      <div className="select-field" ref={selectRef}>
        {label && (
          <label htmlFor={selectId} className="select-label">
            {label}
          </label>
        )}
        <div
          className={`select-trigger ${isOpen ? 'select-trigger-open' : ''} ${error ? 'select-error' : ''}`}
          onClick={() => setIsOpen(!isOpen)}
        >
          <span className="select-placeholder">
            {placeholder || (value ? options.find((o) => String(o.value) === String(value))?.label : '')}
          </span>
          <svg
            className="select-arrow"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>
        {isOpen && (
          <div className="select-dropdown">
            {options.map((option) => (
              <div
                key={option.value}
                className={`select-option ${option.disabled ? 'select-option-disabled' : ''}`}
                onClick={() => option.disabled || handleSelect(option)}
              >
                {option.label}
              </div>
            ))}
          </div>
        )}
        <input
          type="hidden"
          value={value ?? ''}
          onChange={onChange as any}
        />
        {error && (
          <p className="input-error-text">{error}</p>
        )}
        {!error && helperText && (
          <p className="input-helper-text">{helperText}</p>
        )}
      </div>
    );
  }
);
Select.displayName = 'Select';