import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '../../lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none select-none',
  {
    variants: {
      variant: {
        default:
          'bg-indigo-600 text-white hover:bg-indigo-700 active:bg-indigo-800 shadow-sm',
        secondary:
          'bg-zinc-700 text-zinc-100 hover:bg-zinc-600',
        outline:
          'border border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800',
        ghost:
          'text-zinc-300 hover:bg-zinc-800',
        destructive:
          'bg-red-500 text-white hover:bg-red-600 shadow-sm',
        success:
          'bg-emerald-500 text-white hover:bg-emerald-600 shadow-sm',
        link:
          'text-indigo-600 underline-offset-4 hover:underline dark:text-indigo-400',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        default: 'h-10 px-4 py-2',
        lg: 'h-12 px-6 text-base',
        icon: 'h-9 w-9',
        'icon-sm': 'h-7 w-7',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props}
    />
  )
)
Button.displayName = 'Button'

export { Button, buttonVariants }
