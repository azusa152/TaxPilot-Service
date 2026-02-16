import { Home, Wallet, UserCircle, Upload, Calculator } from "lucide-react";

export interface NavItem {
  href: string;
  labelKey: string;
  icon: React.ReactNode;
}

export const navItems: NavItem[] = [
  { href: "/", labelKey: "home", icon: <Home className="h-4 w-4" /> },
  { href: "/income", labelKey: "income", icon: <Wallet className="h-4 w-4" /> },
  {
    href: "/profile",
    labelKey: "profile",
    icon: <UserCircle className="h-4 w-4" />,
  },
  {
    href: "/upload",
    labelKey: "upload",
    icon: <Upload className="h-4 w-4" />,
  },
  {
    href: "/calculate",
    labelKey: "calculate",
    icon: <Calculator className="h-4 w-4" />,
  },
];
