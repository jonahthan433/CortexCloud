import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useState } from 'react';
import FadeIn from './FadeIn';

const CaseStudiesSection = () => {
  const [activeSlide, setActiveSlide] = useState(0);

  const caseStudies = [
    {
      company: 'Vizion Autos',
      description: 'CortexCloud helped Vizion Autos automate lead follow-ups, finance applications, and WhatsApp responses, resulting in a 52% increase in qualified leads and a 40% faster deal conversion rate.',
      stat1: '52%',
      stat1Label: 'More qualified leads',
      stat2: '40%',
      stat2Label: 'Faster conversion',
    },
    {
      company: 'Hardyz Supermarket',
      description: 'CortexCloud helped Hardyz Supermarket automate customer loyalty campaigns, online orders, and restock alerts, leading to a 38% increase in repeat purchases.',
      stat1: '38%',
      stat1Label: 'Repeat purchases',
      stat2: '27%',
      stat2Label: 'Sales boost',
    },
    {
      company: 'Careo AI',
      description: 'CortexCloud helped Careo AI automate patient bookings, follow-ups, and reminders resulting in a 43% increase in appointments and 25+ staff hours saved weekly.',
      stat1: '43%',
      stat1Label: 'More appointments',
      stat2: '25+',
      stat2Label: 'Hours saved weekly',
    },
  ];

  const nextSlide = () => {
    setActiveSlide((prev) => (prev + 1) % caseStudies.length);
  };

  const prevSlide = () => {
    setActiveSlide((prev) => (prev - 1 + caseStudies.length) % caseStudies.length);
  };

  return (
    <section className="py-16 md:py-32 relative overflow-hidden">
      <div className="absolute inset-0 bg-secondary/20" />
      
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Section Header */}
        <FadeIn>
          <div className="text-center mb-8 md:mb-16">
            <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary mb-4">
              Our Work
            </span>
            <h2 className="text-mobile-title lg:text-5xl font-bold font-display">
              Our Work. <span className="text-gradient">Our Pride.</span>
            </h2>
          </div>
        </FadeIn>

        {/* Case Study Carousel */}
        <div className="relative max-w-4xl mx-auto">
          <FadeIn>
            <div className="glass-strong rounded-2xl p-6 md:p-12">
              <div className="space-y-4 md:space-y-6" key={activeSlide}>
                <h3 className="text-xl md:text-3xl font-bold font-display text-gradient">
                  {caseStudies[activeSlide].company}
                </h3>
                <p className="text-muted-foreground text-sm md:text-lg">
                  {caseStudies[activeSlide].description}
                </p>
                
                {/* Stats */}
                <div className="grid grid-cols-2 gap-4 md:gap-8 pt-4 md:pt-6">
                  <div className="text-center p-3 md:p-4 glass rounded-xl">
                    <p className="text-2xl md:text-4xl font-bold text-gradient">
                      {caseStudies[activeSlide].stat1}
                    </p>
                    <p className="text-xs md:text-sm text-muted-foreground mt-1">
                      {caseStudies[activeSlide].stat1Label}
                    </p>
                  </div>
                  <div className="text-center p-3 md:p-4 glass rounded-xl">
                    <p className="text-2xl md:text-4xl font-bold text-gradient">
                      {caseStudies[activeSlide].stat2}
                    </p>
                    <p className="text-xs md:text-sm text-muted-foreground mt-1">
                      {caseStudies[activeSlide].stat2Label}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </FadeIn>

          {/* Navigation */}
          <div className="flex items-center justify-center gap-4 mt-6 md:mt-8">
            <button
              onClick={prevSlide}
              className="w-12 h-12 rounded-full glass flex items-center justify-center hover:bg-secondary/50 transition-colors touch-manipulation active:scale-95"
              aria-label="Previous slide"
            >
              <ChevronLeft size={24} />
            </button>
            
            <div className="flex gap-2">
              {caseStudies.map((_, index) => (
                <button
                  key={index}
                  onClick={() => setActiveSlide(index)}
                  className={`h-3 rounded-full transition-all duration-300 touch-manipulation ${
                    activeSlide === index
                      ? 'bg-primary w-8'
                      : 'bg-muted w-3 hover:bg-muted-foreground'
                  }`}
                  aria-label={`Go to slide ${index + 1}`}
                />
              ))}
            </div>
            
            <button
              onClick={nextSlide}
              className="w-12 h-12 rounded-full glass flex items-center justify-center hover:bg-secondary/50 transition-colors touch-manipulation active:scale-95"
              aria-label="Next slide"
            >
              <ChevronRight size={24} />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
};

export default CaseStudiesSection;
