import { Mail } from 'lucide-react';
import { Button } from './ui/button';
import cortexLogo from '@/assets/cortexcloud-logo.jpg';

const Footer = () => {
  return (
    <footer className="py-12 md:py-16 relative overflow-hidden border-t border-border">
      <div className="absolute inset-0 bg-gradient-hero opacity-50" />
      
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-12 mb-12">
          {/* Logo & Description */}
          <div className="lg:col-span-2 space-y-6">
            <img 
              src={cortexLogo} 
              alt="CortexCloud" 
              className="h-16 w-auto rounded"
            />
            <p className="text-muted-foreground max-w-md">
              Intelligent AI agents that think, take action and execute. Transform your business with cutting-edge artificial intelligence solutions.
            </p>
          </div>

          {/* Newsletter */}
          <div className="lg:col-span-2 space-y-4">
            <h4 className="font-semibold font-display text-lg">Join Our Newsletter</h4>
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={18} />
                <input
                  type="email"
                  placeholder="Enter your email"
                  className="w-full glass rounded-xl py-3 pl-10 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-primary bg-transparent"
                />
              </div>
              <Button variant="primary">Subscribe</Button>
            </div>
            <p className="text-xs text-muted-foreground">
              * Will send you weekly updates for your better business management.
            </p>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="flex flex-col md:flex-row items-center justify-between gap-4 pt-8 border-t border-border">
          <p className="text-sm text-muted-foreground">
            © Copyright 2025 CortexCloud. All rights reserved.
          </p>
          <div className="flex items-center gap-6">
            <a href="#" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              Contact Us
            </a>
            <a href="#" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              Privacy Policy
            </a>
            <a href="#" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              Terms of Service
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
