export default function Background() {
  return (
    <div className="min-h-screen bg-white absolute inset-0 overflow-hidden">
      {/* Colorful Splotches */}
      <div className="absolute inset-0 pointer-events-none">
        {/* Large UTD secondary splotch - visible on all screens */}
        <div className="absolute top-20 left-10 w-112 h-112 bg-utd-secondary/45 rounded-full blur-3xl"></div>

        {/* Medium UTD primary splotch - hidden on mobile, visible on medium+ */}
        <div className="hidden md:block absolute top-36 right-8 w-80 h-80 bg-utd-primary/45 rounded-full blur-2xl"></div>

        {/* Small UTD secondary splotch - hidden on mobile, visible on medium+ */}
        <div className="hidden md:block absolute bottom-32 left-1/4 w-64 h-64 bg-utd-secondary/35 rounded-full blur-xl"></div>

        {/* Medium UTD primary splotch - hidden on mobile and medium, visible on large+ */}
        <div className="hidden lg:block absolute bottom-20 right-1/3 w-72 h-72 bg-utd-primary/30 rounded-full blur-2xl"></div>

        {/* Small accent splotch - hidden on mobile and medium, visible on large+ */}
        <div className="hidden lg:block absolute top-5/8 left-13/16 w-48 h-48 bg-utd-secondary/70 rounded-full blur-lg"></div>
      </div>
    </div>
  );
}
