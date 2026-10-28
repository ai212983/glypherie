import * as React from "react"
import { Slot } from "radix-ui"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "utils"

const studioCard = "studio-card gap-3 rounded-[12px] border-border bg-card p-[14px] font-studio text-card-foreground shadow-studio-card"
const cardVariants = cva("group/card flex flex-col border", {
  variants: {
    variant: {
      default: studioCard,
      studio: studioCard,
      plain: "gap-6 rounded-xl bg-card py-6 text-card-foreground shadow-sm",
    },
  },
  defaultVariants: { variant: "default" },
})

type CardVariant = NonNullable<VariantProps<typeof cardVariants>["variant"]>
const CardVariantContext = React.createContext<CardVariant>("default")

function Card({ className, variant = "default", ...props }: React.ComponentProps<"div"> & VariantProps<typeof cardVariants>) {
  const resolved = variant ?? "default"
  return (
    <CardVariantContext.Provider value={resolved}>
      <div
        data-slot="card"
        data-variant={resolved}
        className={cn(cardVariants({ variant: resolved, className }))}
        {...props}
      />
    </CardVariantContext.Provider>
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  const studio = React.useContext(CardVariantContext) !== "plain"
  return (
    <div
      data-slot="card-header"
      className={cn(
        "@container/card-header grid auto-rows-min items-start has-data-[slot=card-action]:grid-cols-[1fr_auto]",
        studio ? "grid-rows-[auto] gap-0 border-b border-border/80 px-0 pb-[6px]" : "grid-rows-[auto_auto] gap-2 px-6 [.border-b]:pb-6",
        className
      )}
      {...props}
    />
  )
}

function CardTitle({ className, asChild = false, ...props }: React.ComponentProps<"div"> & { asChild?: boolean }) {
  const studio = React.useContext(CardVariantContext) !== "plain"
  const Comp = asChild ? Slot.Root : "div"
  return (
    <Comp
      data-slot="card-title"
      className={cn(
        "leading-none font-semibold",
        studio && "flex items-center gap-[6px] font-studio text-[10px] leading-4 font-bold tracking-[0.5px] text-studio-heading uppercase",
        className
      )}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

function CardAction({ className, ...props }: React.ComponentProps<"div">) {
  const studio = React.useContext(CardVariantContext) !== "plain"
  return (
    <div
      data-slot="card-action"
      className={cn(
        "col-start-2 row-start-1 self-start justify-self-end",
        studio ? "row-span-1" : "row-span-2",
        className
      )}
      {...props}
    />
  )
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  const studio = React.useContext(CardVariantContext) !== "plain"
  return (
    <div
      data-slot="card-content"
      className={cn(studio ? "px-0" : "px-6", className)}
      {...props}
    />
  )
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  const studio = React.useContext(CardVariantContext) !== "plain"
  return (
    <div
      data-slot="card-footer"
      className={cn(
        "flex items-center",
        studio ? "border-t border-border px-0 pt-[8px]" : "px-6 [.border-t]:pt-6",
        className
      )}
      {...props}
    />
  )
}

export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardAction,
  CardDescription,
  CardContent,
}
