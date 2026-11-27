import React from 'react';

export interface RadioOption {
  value: string | number;
  label: string;
  disabled?: boolean;
}

export interface RadioProps {
  options: RadioOption[];
  value: string | number | null;
  onChange: (value: string | number) => void;
  label?: string;
  error?: string;
  name?: string;
}

export const Radio: React.FC<RadioProps> = ({
  options,
  value,
  onChange,
  label,
  error,
  name = 'radio-group',
}) => {
  return (
    <div className={`radio-field ${error ? 'radio-error' : ''}`}>
      {label && <label className="radio-label">{label}</label>}
      <div className="radio-options">
        {options.map((option) => (
          <label key={option.value} className={`radio-option ${option.disabled ? 'radio-disabled' : ''}`}>
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={String(option.value) === String(value)}
              disabled={option.disabled}
              onChange={() => !option.disabled && onChange(option.value)}
              className="radio-input"
            />
            <span className="radio-custom"></span>
            <span className="radio-text">{option.label}</span>
          </label>
        ))}
      </div>
      {error && <span className="input-error-text">{error}</span>}
    </div>
  );
};