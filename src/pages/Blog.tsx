import { Calendar, Clock, ArrowRight, Tag } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import PageTransition from '@/components/PageTransition';
import FadeIn from '@/components/FadeIn';

const blogPosts = [
  {
    id: 1,
    title: 'The Future of AI-Powered Customer Support',
    excerpt: 'Discover how artificial intelligence is revolutionizing the way businesses interact with their customers, creating more personalized and efficient support experiences.',
    category: 'AI Trends',
    date: 'Dec 15, 2024',
    readTime: '5 min read',
    image: 'https://images.unsplash.com/photo-1531746790731-6c087fecd65a?w=600&h=400&fit=crop',
    featured: true,
  },
  {
    id: 2,
    title: 'How to Implement AI Chatbots Without Losing the Human Touch',
    excerpt: 'Learn the best practices for deploying AI chatbots that enhance customer experience while maintaining authentic human connections.',
    category: 'Best Practices',
    date: 'Dec 12, 2024',
    readTime: '7 min read',
    image: 'https://images.unsplash.com/photo-1676299081847-824916de030a?w=600&h=400&fit=crop',
    featured: false,
  },
  {
    id: 3,
    title: 'Case Study: 50% Cost Reduction with AI Automation',
    excerpt: 'See how a leading e-commerce company transformed their support operations and achieved significant cost savings using our AI platform.',
    category: 'Case Studies',
    date: 'Dec 10, 2024',
    readTime: '4 min read',
    image: 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=600&h=400&fit=crop',
    featured: false,
  },
  {
    id: 4,
    title: 'Understanding Natural Language Processing in 2024',
    excerpt: 'A deep dive into the latest advancements in NLP technology and what they mean for business applications.',
    category: 'Technology',
    date: 'Dec 8, 2024',
    readTime: '8 min read',
    image: 'https://images.unsplash.com/photo-1677442136019-21780ecad995?w=600&h=400&fit=crop',
    featured: false,
  },
  {
    id: 5,
    title: 'Building Trust: AI Transparency in Customer Interactions',
    excerpt: 'Why being upfront about AI usage builds stronger customer relationships and how to implement transparent AI policies.',
    category: 'Best Practices',
    date: 'Dec 5, 2024',
    readTime: '6 min read',
    image: 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=600&h=400&fit=crop',
    featured: false,
  },
  {
    id: 6,
    title: 'The ROI of AI: Measuring Success in Customer Support',
    excerpt: 'Key metrics and KPIs to track when implementing AI solutions in your customer support workflow.',
    category: 'Business',
    date: 'Dec 2, 2024',
    readTime: '5 min read',
    image: 'https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=600&h=400&fit=crop',
    featured: false,
  },
];

const categories = ['All', 'AI Trends', 'Best Practices', 'Case Studies', 'Technology', 'Business'];

const Blog = () => {
  const featuredPost = blogPosts.find(post => post.featured);
  const regularPosts = blogPosts.filter(post => !post.featured);

  return (
    <PageTransition>
      <div className="min-h-screen bg-background">
        <Navbar />
        
        <main className="pt-20 md:pt-32">
          {/* Hero Section */}
          <section className="py-12 md:py-24 relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-hero" />
            <div className="absolute top-1/2 right-1/4 w-64 md:w-96 h-64 md:h-96 bg-accent/10 rounded-full blur-3xl animate-pulse-glow" />
            
            <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
              <FadeIn>
                <div className="max-w-3xl mx-auto text-center space-y-4 md:space-y-6">
                  <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary">
                    Our Blog
                  </span>
                  <h1 className="text-mobile-hero font-bold font-display">
                    Insights & <span className="text-gradient">Ideas</span>
                  </h1>
                  <p className="text-mobile-body text-muted-foreground">
                    Stay up to date with the latest trends in AI, customer support automation, and digital transformation.
                  </p>
                </div>
              </FadeIn>
            </div>
          </section>

          {/* Categories */}
          <section className="py-6 border-b border-border/50">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <FadeIn>
                <div className="flex flex-wrap gap-2 justify-center">
                  {categories.map((category, index) => (
                    <button
                      key={category}
                      className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
                        index === 0 
                          ? 'bg-gradient-primary text-primary-foreground' 
                          : 'glass hover:bg-secondary'
                      }`}
                    >
                      {category}
                    </button>
                  ))}
                </div>
              </FadeIn>
            </div>
          </section>

          {/* Featured Post */}
          {featuredPost && (
            <section className="py-12 md:py-16">
              <div className="container mx-auto px-4 sm:px-6 lg:px-8">
                <FadeIn>
                  <div className="relative group cursor-pointer">
                    <div className="absolute -inset-1 bg-gradient-primary rounded-2xl opacity-20 blur-xl group-hover:opacity-30 transition-opacity" />
                    <div className="relative glass-strong rounded-2xl overflow-hidden">
                      <div className="grid md:grid-cols-2 gap-6 md:gap-8">
                        <div className="aspect-video md:aspect-auto md:h-full">
                          <img 
                            src={featuredPost.image} 
                            alt={featuredPost.title}
                            className="w-full h-full object-cover"
                          />
                        </div>
                        <div className="p-6 md:p-8 flex flex-col justify-center">
                          <div className="flex items-center gap-2 mb-4">
                            <span className="bg-gradient-primary text-primary-foreground px-3 py-1 rounded-full text-xs font-medium">
                              Featured
                            </span>
                            <span className="glass px-3 py-1 rounded-full text-xs font-medium">
                              {featuredPost.category}
                            </span>
                          </div>
                          <h2 className="text-2xl md:text-3xl font-bold font-display mb-4 group-hover:text-primary transition-colors">
                            {featuredPost.title}
                          </h2>
                          <p className="text-muted-foreground mb-6">
                            {featuredPost.excerpt}
                          </p>
                          <div className="flex items-center gap-4 text-sm text-muted-foreground mb-6">
                            <span className="flex items-center gap-1">
                              <Calendar size={16} />
                              {featuredPost.date}
                            </span>
                            <span className="flex items-center gap-1">
                              <Clock size={16} />
                              {featuredPost.readTime}
                            </span>
                          </div>
                          <Button variant="primary" className="w-fit">
                            Read Article <ArrowRight size={18} className="ml-2" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                </FadeIn>
              </div>
            </section>
          )}

          {/* Blog Grid */}
          <section className="py-12 md:py-24">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <FadeIn>
                <h2 className="text-mobile-title font-bold font-display mb-8">Latest Articles</h2>
              </FadeIn>
              
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 md:gap-8">
                {regularPosts.map((post, index) => (
                  <FadeIn key={post.id} delay={index * 0.1}>
                    <article className="glass-strong rounded-2xl overflow-hidden group cursor-pointer hover:-translate-y-2 transition-all duration-300">
                      <div className="aspect-video overflow-hidden">
                        <img 
                          src={post.image} 
                          alt={post.title}
                          className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500"
                        />
                      </div>
                      <div className="p-6">
                        <div className="flex items-center gap-2 mb-3">
                          <Tag size={14} className="text-primary" />
                          <span className="text-xs font-medium text-primary">{post.category}</span>
                        </div>
                        <h3 className="text-lg font-bold font-display mb-3 group-hover:text-primary transition-colors line-clamp-2">
                          {post.title}
                        </h3>
                        <p className="text-muted-foreground text-sm mb-4 line-clamp-2">
                          {post.excerpt}
                        </p>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <Calendar size={14} />
                            {post.date}
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock size={14} />
                            {post.readTime}
                          </span>
                        </div>
                      </div>
                    </article>
                  </FadeIn>
                ))}
              </div>

              {/* Load More */}
              <FadeIn delay={0.5}>
                <div className="text-center mt-12">
                  <Button variant="outline" size="lg">
                    Load More Articles
                  </Button>
                </div>
              </FadeIn>
            </div>
          </section>

          {/* Newsletter CTA */}
          <section className="py-12 md:py-24 relative">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <FadeIn>
                <div className="relative">
                  <div className="absolute -inset-1 bg-gradient-primary rounded-2xl opacity-20 blur-xl" />
                  <div className="relative glass-strong rounded-2xl p-8 md:p-12 text-center">
                    <h2 className="text-mobile-title font-bold font-display mb-4">
                      Stay in the <span className="text-gradient">Loop</span>
                    </h2>
                    <p className="text-muted-foreground text-mobile-body max-w-2xl mx-auto mb-8">
                      Subscribe to our newsletter and get the latest AI insights, tips, and updates delivered straight to your inbox.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center max-w-md mx-auto">
                      <input
                        type="email"
                        placeholder="Enter your email"
                        className="glass border-border/50 focus:border-primary h-14 px-4 rounded-xl text-base flex-1 bg-transparent outline-none"
                      />
                      <Button variant="primary" size="lg" className="h-14">
                        Subscribe
                      </Button>
                    </div>
                  </div>
                </div>
              </FadeIn>
            </div>
          </section>
        </main>

        <Footer />
      </div>
    </PageTransition>
  );
};

export default Blog;