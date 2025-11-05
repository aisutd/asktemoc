"use client";

import * as React from "react";
import Link from "next/link";
import Image from "next/image";

import { NavigationMenu } from "@/components/ui/navigation-menu";

export default function Navbar() {
  return (
    <NavigationMenu
      viewport={false}
      className="p-4 w-full max-w-none justify-start"
    >
      <Image src="/temochead.svg" alt="logo" width={50} height={50} />
      <h1 className="text-xl font-bold text-utd-primary">Ask Temoc</h1>
      <Link
        href="/"
        className="group inline-flex h-9 w-max items-center justify-center rounded-md bg-background px-4 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground focus-visible:ring-ring/50 outline-none transition-[color,box-shadow] focus-visible:ring-[3px] focus-visible:outline-1 m-4"
      >
        Home
      </Link>
    </NavigationMenu>
  );
}
