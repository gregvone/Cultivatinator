import {
  LayoutDashboard,
  Dna,
  FlaskConical,
  Sprout,
  PackagePlus,
  BookOpen,
  ChartNoAxesCombined,
  Settings2,
  Thermometer,
} from "lucide-react";
export const navigation = [
  { path: "/", title: "Dashboard", icon: LayoutDashboard },
  { path: "/culture-library", title: "Culture Library", icon: Dna },
  { path: "/genetics", title: "Genetics", icon: Dna },
  { path: "/laboratory", title: "Laboratory", icon: FlaskConical },
  { path: "/cultivation", title: "Cultivation", icon: Sprout },
  { path: "/environment", title: "Environment", icon: Thermometer },
  { path: "/acquisitions", title: "Acquisitions", icon: PackagePlus },
  { path: "/recipes", title: "Recipes", icon: BookOpen },
  { path: "/reports", title: "Reports", icon: ChartNoAxesCombined },
  { path: "/settings", title: "Settings", icon: Settings2 },
];
