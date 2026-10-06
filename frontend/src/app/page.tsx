import Background from "@/components/ui/background";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import Image from "next/image";

export default function Home() {
  return (
    <div className="relative min-h-screen">
      <Background />
      <div className="relative z-10 flex flex-col px-4 sm:px-8 md:px-16 lg:px-24 xl:px-40 py-8 sm:py-16 md:py-20 lg:py-30">
        <h1 className="text-3xl sm:text-4xl md:text-5xl lg:text-6xl xl:text-7xl 2xl:text-8xl font-bold text-black mb-4 sm:mb-6 md:mb-8 max-w-xs sm:max-w-md md:max-w-2xl lg:max-w-4xl xl:max-w-6xl">
          Wave <u className="text-utd-primary">goodbye</u> to <br />
          advisors <span className="text-utd-primary/30">
            ghosting
          </span> you. <br />
          Ask Temoc.
        </h1>
        <div className="flex flex-col sm:flex-row justify-start gap-4 sm:gap-6 md:gap-8 lg:gap-12 xl:gap-16 mt-6 sm:mt-8 md:mt-10">
          <Button
            className="bg-utd-secondary hover:bg-utd-primary/80 w-full sm:w-auto max-w-40 px-4 sm:px-6 md:px-8 lg:px-12 xl:px-20 py-3 sm:py-4 md:py-6 lg:py-8 text-sm sm:text-base md:text-lg"
            asChild
          >
            <Link href="/chat">Get Started</Link>
          </Button>
          <Button
            className="bg-utd-secondary hover:bg-utd-primary/80 sm:w-auto max-w-40 px-4 sm:px-6 md:px-8 lg:px-12 xl:px-20 py-3 sm:py-4 md:py-6 lg:py-8 text-sm sm:text-base md:text-lg"
            asChild
          >
            <Link href="/">Learn More</Link>
          </Button>
        </div>
      </div>

      {/* Temoc Image */}
      <div className="absolute top-3/8 right-8 lg:right-16 xl:right-24 transform -translate-y-1/2 hidden lg:block">
        <Image
          src="/temocfull.svg"
          alt="Temoc Mascot"
          width={300}
          height={300}
          className="w-64 lg:w-80 xl:w-96"
          priority
        />
      </div>
    </div>
  );
}
