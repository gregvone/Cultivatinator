import {
  LayoutDashboard,
  Dna,
  FlaskConical,
  Sprout,
  Boxes,
  ChartNoAxesCombined,
  Settings2,
} from "lucide-react";
export const navigation = [
  { path: "/", title: "Dashboard", icon: LayoutDashboard },
  { path: "/culture-library", title: "Culture Library", icon: Dna },
  { path: "/laboratory", title: "Laboratory", icon: FlaskConical },
  { path: "/cultivation", title: "Cultivation", icon: Sprout },
  { path: "/inventory", title: "Inventory", icon: Boxes },
  { path: "/reports", title: "Reports", icon: ChartNoAxesCombined },
  { path: "/settings", title: "Settings", icon: Settings2 },
];
