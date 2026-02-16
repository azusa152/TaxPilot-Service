import { Skeleton } from "@/components/ui/Skeleton";

interface FormSkeletonProps {
  fields?: number;
}

export function FormSkeleton({ fields = 5 }: FormSkeletonProps) {
  return (
    <div role="status" aria-label="Loading" className="mx-auto max-w-lg space-y-6">
      {/* Title skeleton */}
      <div className="flex items-center justify-between">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-9 w-24" />
      </div>

      {/* Field skeletons */}
      <div className="space-y-4">
        {Array.from({ length: fields }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-10 w-full" />
          </div>
        ))}
      </div>

      {/* Button skeleton */}
      <Skeleton className="h-10 w-24" />
    </div>
  );
}
