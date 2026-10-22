import type * as React from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const meta = {
  title: "UI/Card",
  component: Card,
  args: { className: "w-80" },
  argTypes: { variant: { control: "select", options: ["default", "studio", "plain"] } },
  render: (args) => (
    <Card {...args}>
      <CardHeader>
        <CardTitle>Roboto</CardTitle>
        <CardDescription>Saved font settings</CardDescription>
        <CardAction><Badge variant="secondary">Variable</Badge></CardAction>
      </CardHeader>
      <CardContent>
        <p>The quick brown fox jumps over the lazy dog.</p>
      </CardContent>
      <CardFooter>
        <Button variant="outline">Add variant</Button>
      </CardFooter>
    </Card>
  ),
} satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Plain: Story = { args: { variant: "plain" } };

function CardContents({ name, children }: { name: string; children?: React.ReactNode }) {
  return <>
    <CardHeader>
      <CardTitle asChild><h2>{name}</h2></CardTitle>
      <CardAction><Button size="xs">Action</Button></CardAction>
    </CardHeader>
    <CardContent>{children ?? "Card content"}</CardContent>
    <CardFooter>Footer</CardFooter>
  </>;
}

export const NestedVariants: Story = {
  render: () => (
    <div className="flex gap-6 p-4">
      <Card data-card-fixture="outer-default" className="w-96">
        <CardContents name="App default">
          <Card variant="plain" data-card-fixture="nested-plain">
            <CardContents name="Plain nested card">
              <Card data-card-fixture="nested-default">
                <CardContents name="Nested app default" />
              </Card>
            </CardContents>
          </Card>
        </CardContents>
      </Card>
      <Card variant="plain" data-card-fixture="standalone-plain" className="w-96">
        <CardContents name="Standalone plain card" />
      </Card>
    </div>
  ),
};
