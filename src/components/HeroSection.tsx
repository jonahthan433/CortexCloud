import { Link } from 'react-router-dom';
import { Button } from './ui/button';
import ChatMockup from './ChatMockup';
import FadeIn from './FadeIn';

const HeroSection = () => {
  return (
    <section className="relative min-h-screen pt-20 md:pt-32 pb-16 overflow-hidden">
      {/* Background Effects */}
      <div className="absolute inset-0 bg-gradient-hero" />
      <div className="absolute top-1/4 left-1/4 w-64 md:w-96 h-64 md:h-96 bg-primary/10 rounded-full blur-3xl animate-pulse-glow" />
      <div className="absolute bottom-1/4 right-1/4 w-48 md:w-64 h-48 md:h-64 bg-accent/10 rounded-full blur-3xl animate-pulse-glow" style={{ animationDelay: '1.5s' }} />
      
      {/* Grid Pattern Overlay */}
      <div className="absolute inset-0 opacity-20">
        <div className="absolute inset-0" style={{
          backgroundImage: `radial-gradient(circle at 1px 1px, hsl(var(--muted-foreground) / 0.3) 1px, transparent 0)`,
          backgroundSize: '40px 40px'
        }} />
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="grid lg:grid-cols-2 gap-8 lg:gap-16 items-center">
          {/* Left Content */}
          <FadeIn>
            <div className="space-y-6 md:space-y-8 text-center lg:text-left">
              <h1 className="text-mobile-hero xl:text-7xl font-bold font-display leading-tight">
                Meet your new{' '}
                <span className="text-gradient">AI-Powered</span>{' '}
                team.
              </h1>
              
              <p className="text-mobile-body text-muted-foreground max-w-xl mx-auto lg:mx-0">
                Automate tasks, scale customer service, and boost productivity with intelligent AI agents that think, take action and execute. <span className="text-foreground font-medium">Grow Sales. Cut Costs. Save Time.</span>
              </p>

              <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 justify-center lg:justify-start">
                <Button variant="primary" size="xl" className="w-full sm:w-auto min-h-[56px] text-base" asChild>
                  <Link to="/contact">Book a Call</Link>
                </Button>
                <Button variant="outline" size="xl" className="w-full sm:w-auto min-h-[56px] text-base">
                  Watch Demo
                </Button>
              </div>
            </div>
          </FadeIn>

          {/* Right Content - Chat Mockup */}
          <FadeIn delay={0.2} className="lg:pl-8">
            <ChatMockup />
          </FadeIn>
        </div>
      </div>
    </section>
  );
};

export default HeroSection;
