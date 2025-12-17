import { Phone } from 'lucide-react';
import { Button } from './ui/button';

const CTASection = () => {
  return (
    <section className="py-20 md:py-32 relative overflow-hidden">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="relative">
          {/* Background Glow */}
          <div className="absolute inset-0 bg-gradient-to-r from-primary/20 to-accent/20 rounded-3xl blur-3xl" />
          
          {/* CTA Card */}
          <div className="relative glass-strong rounded-3xl p-8 md:p-16 text-center overflow-hidden">
            {/* Decorative Elements */}
            <div className="absolute top-8 right-8">
              <Phone size={48} className="text-primary/20" />
            </div>
            <div className="absolute bottom-8 left-8 w-24 h-24 bg-gradient-primary rounded-full opacity-10 blur-xl" />
            
            <div className="relative z-10 max-w-2xl mx-auto space-y-6">
              <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold font-display">
                Let AI do the <span className="text-gradient">heavy lifting.</span>
              </h2>
              <p className="text-muted-foreground text-lg">
                Get your very own AI Agents, working 24/7. They are ready.
              </p>
              <div className="pt-4">
                <Button variant="primary" size="xl">
                  Get Started - Book a Call
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default CTASection;
