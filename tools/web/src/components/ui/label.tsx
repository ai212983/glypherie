import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "utils"
import { Label as LabelPrimitive } from "radix-ui"

const labelVariants = cva(
  "flex items-center gap-2 select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "text-sm leading-none font-medium",
        studio: "text-[10px] leading-4 font-semibold text-muted-foreground uppercase",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Label({
  className,
  variant,
  ...props
}: React.ComponentProps<typeof LabelPrimitive.Root> & VariantProps<typeof labelVariants>) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn(labelVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Label, labelVariants }
