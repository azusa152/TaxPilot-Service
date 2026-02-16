import { redirect } from "next/navigation";

export default function CalculateIndexPage() {
  redirect(`/calculate/${new Date().getFullYear()}`);
}
