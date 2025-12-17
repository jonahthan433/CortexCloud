import { Phone } from 'lucide-react';
import { Button } from './ui/button';
import { Link } from 'react-router-dom';
import FadeIn from './FadeIn';

const CTASection = () => {
  return (
    <section className="py-16 md:py-32 relative overflow-hidden">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <FadeIn>
          <div className="relative">
            {/* Background Glow */}
            <div className="absolute inset-0 bg-gradient-to-r from-primary/20 to-accent/20 rounded-3xl blur-3xl" />
            
            {/* CTA Card */}
            <div className="relative glass-strong rounded-2xl md:rounded-3xl p-6 md:p-16 text-center overflow-hidden">
              {/* Decorative Elements */}
              <div className="absolute top-6 right-6 md:top-8 md:right-8 hidden sm:block">
                <Phone size={48} className="text-primary/20" />
              </div>
              <div className="absolute bottom-6 left-6 md:bottom-8 md:left-8 w-16 h-16 md:w-24 md:h-24 bg-gradient-primary rounded-full opacity-10 blur-xl" />
              
              <div className="relative z-10 max-w-2xl mx-auto space-y-4 md:space-y-6">
                <h2 className="text-2xl sm:text-3xl lg:text-5xl font-bold font-display">
                  Let AI do the <span className="text-gradient">heavy lifting.</span>
                </h2>
                <p className="text-muted-foreground text-mobile-body">
                  Get your very own AI Agents, working 24/7. They are ready.
                </p>
                <div className="pt-2 md:pt-4">
                  <Button variant="primary" size="xl" className="w-full sm:w-auto min-h-[56px] px-8 text-base" asChild>
                    <Link to="/contact">
                      Get Started - Book a Call
                    </Link>
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </FadeIn>
      </div>
    </section>
  );
};

export default CTASection;
