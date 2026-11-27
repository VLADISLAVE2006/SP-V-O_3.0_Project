import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { clsx } from 'clsx';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none',
  {
    variants: {
      variant: {
        primary: 'bg-primary text-white hover:bg-primary-hover focus:ring-primary',
        secondary: 'bg-secondary text-white hover:bg-secondary-hover focus:ring-secondary',
        outline:
          'border border-input bg-background hover:bg-accent hover:text-accent-foreground focus:ring-input',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        danger: 'bg-destructive text-white hover:bg-destructive-hover focus:ring-destructive',
      },
      size: {
        sm: 'h-8 px-2 text-xs',
        md: 'h-10 px-3 py-2',
        lg: 'h-11 px-8',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
  fullWidth?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, children, loading, fullWidth, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={clsx(
          buttonVariants({ variant, size, className }),
          fullWidth && 'w-full',
          loading && 'opacity-70 pointer-events-none'
        )}
        disabled={loading || props.disabled}
        {...props}
      >
        {loading && <span className="loading-spinner">…</span>}
        {children}
      </button>
    );
  }
);
Button.displayName = 'Button';