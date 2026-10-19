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
