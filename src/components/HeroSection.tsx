import { Button } from './ui/button';
import ChatMockup from './ChatMockup';

const HeroSection = () => {
  return (
    <section className="relative min-h-screen pt-24 md:pt-32 pb-16 overflow-hidden">
      {/* Background Effects */}
      <div className="absolute inset-0 bg-gradient-hero" />
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/10 rounded-full blur-3xl animate-pulse-glow" />
      <div className="absolute bottom-1/4 right-1/4 w-64 h-64 bg-accent/10 rounded-full blur-3xl animate-pulse-glow" style={{ animationDelay: '1.5s' }} />
      
      {/* Grid Pattern Overlay */}
      <div className="absolute inset-0 opacity-20">
        <div className="absolute inset-0" style={{
          backgroundImage: `radial-gradient(circle at 1px 1px, hsl(var(--muted-foreground) / 0.3) 1px, transparent 0)`,
          backgroundSize: '40px 40px'
        }} />
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          {/* Left Content */}
          <div className="space-y-8 animate-slide-up">
            <h1 className="text-4xl sm:text-5xl lg:text-6xl xl:text-7xl font-bold font-display leading-tight">
              Meet your new{' '}
              <span className="text-gradient">AI-Powered</span>{' '}
              team.
            </h1>
            
            <p className="text-lg sm:text-xl text-muted-foreground max-w-xl">
              Automate tasks, scale customer service, and boost productivity with intelligent AI agents that think, take action and execute. <span className="text-foreground font-medium">Grow Sales. Cut Costs. Save Time.</span>
            </p>

            <div className="flex flex-col sm:flex-row gap-4">
              <Button variant="primary" size="xl">
                Book a Call
              </Button>
              <Button variant="outline" size="xl">
                Watch Demo
              </Button>
            </div>
          </div>

          {/* Right Content - Chat Mockup */}
          <div className="lg:pl-8 animate-slide-up" style={{ animationDelay: '0.2s' }}>
            <ChatMockup />
          </div>
        </div>
      </div>
    </section>
  );
};

export default HeroSection;
