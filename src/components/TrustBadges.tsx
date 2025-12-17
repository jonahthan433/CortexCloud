const TrustBadges = () => {
  const brands = [
    { name: 'Flexzo', logo: 'FLEXZO' },
    { name: 'Baazex', logo: 'BAAZEX' },
    { name: 'Vizion', logo: 'VIZION' },
    { name: 'Careo', logo: 'CAREO' },
    { name: 'TechFlow', logo: 'TECHFLOW' },
    { name: 'NexGen', logo: 'NEXGEN' },
  ];

  return (
    <section className="py-12 md:py-16 relative overflow-hidden">
      <div className="absolute inset-0 bg-secondary/30" />
      
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="flex flex-col md:flex-row items-center gap-8 md:gap-12">
          <p className="text-muted-foreground text-sm whitespace-nowrap">
            Trusted by <span className="text-foreground font-semibold">1000+</span><br />
            businesses worldwide
          </p>
          
          {/* Scrolling Logos */}
          <div className="flex-1 overflow-hidden">
            <div className="flex items-center gap-12 animate-marquee">
              {[...brands, ...brands].map((brand, index) => (
                <div
                  key={`${brand.name}-${index}`}
                  className="flex-shrink-0 glass px-6 py-3 rounded-lg"
                >
                  <span className="text-lg font-bold font-display tracking-wider text-muted-foreground/80">
                    {brand.logo}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      
      <style>{`
        @keyframes marquee {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .animate-marquee {
          animation: marquee 20s linear infinite;
        }
      `}</style>
    </section>
  );
};

export default TrustBadges;
