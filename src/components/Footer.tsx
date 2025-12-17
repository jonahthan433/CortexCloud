import { Mail } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from './ui/button';
import cortexLogo from '@/assets/cortexcloud-logo.jpg';

const Footer = () => {
  const footerLinks = {
    company: [
      { label: 'About', href: '/about' },
      { label: 'Services', href: '/services' },
      { label: 'Pricing', href: '/pricing' },
      { label: 'Contact', href: '/contact' },
    ],
    resources: [
      { label: 'Blog', href: '#' },
      { label: 'Documentation', href: '#' },
      { label: 'API Reference', href: '#' },
      { label: 'Support', href: '/contact' },
    ],
    legal: [
      { label: 'Privacy Policy', href: '#' },
      { label: 'Terms of Service', href: '#' },
      { label: 'Cookie Policy', href: '#' },
    ],
  };

  return (
    <footer className="py-12 md:py-16 relative overflow-hidden border-t border-border mb-16 md:mb-0">
      <div className="absolute inset-0 bg-gradient-hero opacity-50" />
      
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="grid grid-cols-2 md:grid-cols-2 lg:grid-cols-5 gap-8 md:gap-12 mb-8 md:mb-12">
          {/* Logo & Description */}
          <div className="col-span-2 lg:col-span-2 space-y-4 md:space-y-6">
            <Link to="/" className="inline-block">
              <img 
                src={cortexLogo} 
                alt="CortexCloud" 
                className="h-12 md:h-16 w-auto rounded"
              />
            </Link>
            <p className="text-muted-foreground text-sm md:text-base max-w-md">
              Intelligent AI agents that think, take action and execute. Transform your business with cutting-edge artificial intelligence solutions.
            </p>
            
            {/* Newsletter - Hidden on mobile, shown on tablet+ */}
            <div className="hidden sm:block space-y-3">
              <h4 className="font-semibold font-display text-base">Join Our Newsletter</h4>
              <div className="flex gap-2">
                <div className="flex-1 relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={18} />
                  <input
                    type="email"
                    placeholder="Enter your email"
                    className="w-full glass rounded-xl py-3 pl-10 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-primary bg-transparent"
                  />
                </div>
                <Button variant="primary" className="h-12">Subscribe</Button>
              </div>
            </div>
          </div>

          {/* Company Links */}
          <div>
            <h4 className="font-semibold font-display mb-3 md:mb-4 text-sm md:text-base">Company</h4>
            <ul className="space-y-2 md:space-y-3">
              {footerLinks.company.map((link) => (
                <li key={link.label}>
                  <Link 
                    to={link.href}
                    className="text-muted-foreground hover:text-foreground transition-colors text-sm touch-manipulation py-1 inline-block"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Resources Links */}
          <div>
            <h4 className="font-semibold font-display mb-3 md:mb-4 text-sm md:text-base">Resources</h4>
            <ul className="space-y-2 md:space-y-3">
              {footerLinks.resources.map((link) => (
                <li key={link.label}>
                  <Link 
                    to={link.href}
                    className="text-muted-foreground hover:text-foreground transition-colors text-sm touch-manipulation py-1 inline-block"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Legal Links */}
          <div className="col-span-2 sm:col-span-1">
            <h4 className="font-semibold font-display mb-3 md:mb-4 text-sm md:text-base">Legal</h4>
            <ul className="space-y-2 md:space-y-3">
              {footerLinks.legal.map((link) => (
                <li key={link.label}>
                  <Link 
                    to={link.href}
                    className="text-muted-foreground hover:text-foreground transition-colors text-sm touch-manipulation py-1 inline-block"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Mobile Newsletter */}
        <div className="sm:hidden mb-8 space-y-3">
          <h4 className="font-semibold font-display text-sm">Join Our Newsletter</h4>
          <div className="flex flex-col gap-2">
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={18} />
              <input
                type="email"
                placeholder="Enter your email"
                className="w-full glass rounded-xl py-3 pl-10 pr-4 text-base focus:outline-none focus:ring-2 focus:ring-primary bg-transparent"
              />
            </div>
            <Button variant="primary" className="w-full h-12">Subscribe</Button>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="flex flex-col md:flex-row items-center justify-between gap-4 pt-6 md:pt-8 border-t border-border">
          <p className="text-xs md:text-sm text-muted-foreground text-center md:text-left">
            © Copyright 2025 CortexCloud. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
