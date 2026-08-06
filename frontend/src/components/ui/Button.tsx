import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Link, type LinkProps } from 'react-router-dom';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'lg';

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    'bg-brand-500 text-white hover:bg-brand-600 focus-visible:ring-brand-500 disabled:bg-slate-300 disabled:text-slate-500',
  secondary:
    'border border-slate-300 bg-white text-slate-700 hover:border-brand-500 hover:text-brand-600 focus-visible:ring-brand-500 disabled:border-slate-200 disabled:text-slate-400',
  danger:
    'bg-danger-600 text-white hover:bg-red-700 focus-visible:ring-danger-600 disabled:bg-slate-300 disabled:text-slate-500',
  ghost:
    'text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus-visible:ring-brand-500 disabled:text-slate-300',
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
  lg: 'h-11 px-5 text-sm',
};

const BASE_CLASSES =
  'inline-flex items-center justify-center gap-2 rounded-lg font-bold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:cursor-not-allowed';

export function buttonClassName(variant: ButtonVariant = 'primary', size: ButtonSize = 'md', className = '') {
  return [BASE_CLASSES, VARIANT_CLASSES[variant], SIZE_CLASSES[size], className].filter(Boolean).join(' ');
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
};

export function Button({ variant = 'primary', size = 'md', className = '', type = 'button', ...rest }: ButtonProps) {
  return <button type={type} className={buttonClassName(variant, size, className)} {...rest} />;
}

type LinkButtonProps = LinkProps & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
};

export function LinkButton({ variant = 'primary', size = 'md', className = '', ...rest }: LinkButtonProps) {
  return <Link className={buttonClassName(variant, size, className)} {...rest} />;
}

export default Button;
